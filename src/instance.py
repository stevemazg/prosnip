"""One running ProSnip-Bob.

A second launch of the same version asks the existing process to show its
window. A different version is reported back so the new process can warn
instead of pretending the old window is this one.
"""

import logging
import sys

from PyQt6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

SERVER_NAME = "ProSnip-Bob"
OLDER_LABEL = "an older version"


class Peer:
    """An already-running ProSnip-Bob."""

    def __init__(self, version: str, pid: int | None = None):
        self.version = version or OLDER_LABEL
        self.pid = pid

    def close(self) -> bool:
        """Ask a current build to quit, then terminate the process if it is still there."""
        asked = _send(b"QUIT\n")
        if self.pid and self.pid != _own_pid():
            if _terminate(self.pid):
                return True
        return asked


def try_notify_primary(name: str = SERVER_NAME, timeout_ms: int = 500) -> bool:
    """Ask the running copy to show its window. Used by tests and the tray."""
    return _send(b"SHOW\n", name)


def claim_primary(on_show, on_quit=None, version: str = "", name: str = SERVER_NAME):
    """Return ``(is_primary, server, peer)``.

    ``peer`` is set when another version is already running. The same version
    is asked to show its window and ``peer`` stays None.
    """
    peer = _contact(version, name)
    if peer == "same":
        return False, None, None
    if isinstance(peer, Peer):
        return False, None, peer
    server = listen_for_activation(on_show, on_quit, version, name)
    if server is not None:
        return True, server, None
    peer = _contact(version, name)
    if peer == "same":
        return False, None, None
    if isinstance(peer, Peer):
        return False, None, peer
    log.error("Single-instance listener was not created; continuing anyway")
    return True, None, None


def listen_for_activation(on_show, on_quit=None, version: str = "", name: str = SERVER_NAME):
    QLocalServer.removeServer(name)
    server = QLocalServer()

    def accept():
        _accept(server, on_show, on_quit, version)

    server.newConnection.connect(accept)
    if server.listen(name):
        log.info("Listening for another launch as %s (%s)", name, version or "unversioned")
        return server
    log.error("Could not listen for another launch: %s", server.errorString())
    return None


def release_server(server: QLocalServer | None, name: str = SERVER_NAME) -> None:
    if server is None:
        return
    server_name = server.serverName() or name
    server.close()
    QLocalServer.removeServer(server_name)


def _pump(milliseconds: int) -> None:
    from PyQt6.QtTest import QTest
    QTest.qWait(milliseconds)


def _contact(version: str, name: str):
    """Return ``'same'``, a :class:`Peer`, or None when nothing is listening."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    reply = ""
    connected = False
    for _ in range(16):
        _pump(25)
        if socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            connected = True
        if socket.isOpen():
            reply += bytes(socket.readAll()).decode("utf-8", "replace")
        if "VERSION" in reply:
            break
        if socket.state() == QLocalSocket.LocalSocketState.UnconnectedState and not connected:
            return None
    if not connected and "VERSION" not in reply:
        return None
    pid = _server_pid(socket)
    peer_version = ""
    if "VERSION" in reply:
        line = reply.strip().splitlines()[0]
        parts = line.split()
        peer_version = parts[1] if len(parts) > 1 else ""
    if peer_version and peer_version == version:
        socket.write(b"SHOW\n")
        socket.flush()
        _pump(40)
        socket.disconnectFromServer()
        return "same"
    socket.disconnectFromServer()
    if not peer_version:
        peer_version = _file_version(pid) or OLDER_LABEL
    return Peer(peer_version, pid)


def _send(payload: bytes, name: str = SERVER_NAME) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(name)
    connected = False
    for _ in range(16):
        _pump(25)
        if socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            connected = True
            break
        if socket.state() == QLocalSocket.LocalSocketState.UnconnectedState and _ > 2:
            return False
    if not connected:
        return False
    socket.write(payload)
    socket.flush()
    _pump(40)
    socket.disconnectFromServer()
    return True


def _accept(server: QLocalServer, on_show, on_quit, version: str) -> None:
    connection = server.nextPendingConnection()
    if connection is None:
        return
    held = getattr(server, "_connections", None)
    if held is None:
        held = []
        server._connections = held
    held.append(connection)
    connection._buffer = ""
    try:
        connection.write(f"VERSION {version}\n".encode("utf-8"))
        connection.flush()
    except Exception:
        log.exception("Could not answer the other launch")

    def ready(conn=connection):
        conn._buffer += bytes(conn.readAll()).decode("utf-8", "replace")
        try:
            if "QUIT" in conn._buffer:
                log.info("The other launch asked this copy to quit")
                if on_quit is not None:
                    on_quit()
                conn.disconnectFromServer()
                if conn in held:
                    held.remove(conn)
                conn.deleteLater()
            elif "SHOW" in conn._buffer:
                log.info("Second launch requested the existing window")
                if on_show is not None:
                    on_show()
                conn.disconnectFromServer()
                if conn in held:
                    held.remove(conn)
                conn.deleteLater()
        except Exception:
            log.exception("Could not handle the other launch")

    connection.readyRead.connect(ready)
    if connection.bytesAvailable():
        ready()


def _own_pid() -> int:
    return int(__import__("os").getpid())


def _server_pid(socket: QLocalSocket) -> int | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        handle = int(socket.socketDescriptor())
        if handle <= 0:
            return None
        pid = wintypes.DWORD()
        ok = ctypes.windll.kernel32.GetNamedPipeServerProcessId(
            wintypes.HANDLE(handle),
            ctypes.byref(pid),
        )
        if ok:
            return int(pid.value)
    except Exception:
        log.exception("Could not read the running ProSnip-Bob process")
    return None


def _file_version(pid: int | None) -> str | None:
    if sys.platform != "win32" or not pid or pid == _own_pid():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.windll.kernel32
        version = ctypes.windll.version
        access = 0x1000
        handle = kernel.OpenProcess(access, False, pid)
        if not handle:
            return None
        try:
            size = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(size.value)
            if not kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return None
            path = buf.value
        finally:
            kernel.CloseHandle(handle)
        info_size = version.GetFileVersionInfoSizeW(path, None)
        if not info_size:
            return None
        data = ctypes.create_string_buffer(info_size)
        if not version.GetFileVersionInfoW(path, 0, info_size, data):
            return None
        value = ctypes.c_void_p()
        length = wintypes.UINT()
        block = "\\StringFileInfo\\040904B0\\FileVersion"
        if not version.VerQueryValueW(data, block, ctypes.byref(value), ctypes.byref(length)):
            return None
        if not value.value or length.value < 1:
            return None
        return ctypes.wstring_at(value.value, length.value - 1)
    except Exception:
        log.exception("Could not read the running ProSnip-Bob version")
        return None


def _terminate(pid: int) -> bool:
    if sys.platform != "win32" or pid == _own_pid():
        return False
    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x0001, False, pid)
        if not handle:
            return False
        try:
            return bool(kernel.TerminateProcess(handle, 0))
        finally:
            kernel.CloseHandle(handle)
    except Exception:
        log.exception("Could not close the other ProSnip-Bob")
        return False
