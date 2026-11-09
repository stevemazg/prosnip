"""One running ProSnip-Bob.

A second launch connects to the existing process and asks it to show its
window, instead of starting another copy that cannot register the hotkey.
"""

import logging

from PyQt6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

SERVER_NAME = "ProSnip-Bob"


def try_notify_primary(name: str = SERVER_NAME, timeout_ms: int = 500) -> bool:
    """Return True if an existing instance accepted a show request."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.disconnectFromServer()
    return True


def listen_for_activation(on_show, name: str = SERVER_NAME) -> QLocalServer | None:
    """Listen for later launches. The caller must already know it is primary."""
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.newConnection.connect(lambda: _accept(server, on_show))
    if server.listen(name):
        log.info("Listening for another launch as %s", name)
        return server
    log.error("Could not listen for another launch: %s", server.errorString())
    return None


def claim_primary(on_show, name: str = SERVER_NAME) -> tuple[bool, QLocalServer | None]:
    """Return ``(is_primary, server)``.

    When another instance is already running it is asked to bring its window
    to the front and this call returns ``(False, None)``.
    """
    if try_notify_primary(name):
        log.info("ProSnip-Bob is already running; bringing that window to the front")
        return False, None
    server = listen_for_activation(on_show, name)
    if server is not None:
        return True, server
    # Lost a race with a launch that started in the same moment.
    if try_notify_primary(name):
        log.info("ProSnip-Bob is already running; bringing that window to the front")
        return False, None
    log.error("Single-instance listener was not created; continuing anyway")
    return True, None


def release_server(server: QLocalServer | None, name: str = SERVER_NAME) -> None:
    if server is None:
        return
    server_name = server.serverName() or name
    server.close()
    QLocalServer.removeServer(server_name)


def _accept(server: QLocalServer, on_show) -> None:
    connection = server.nextPendingConnection()
    if connection is not None:
        connection.disconnectFromServer()
        connection.deleteLater()
    log.info("Second launch requested the existing window")
    try:
        on_show()
    except Exception:
        log.exception("Could not show the existing window")
