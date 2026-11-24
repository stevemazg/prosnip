@echo off
set "NOPAUSE="
if /I "%~1"=="/nopause" set "NOPAUSE=1"
python scripts\write_version_info.py
if errorlevel 1 goto :failed
pyinstaller --noconfirm --clean --onedir --windowed --noupx --name ProSnip-Bob --exclude-module tkinter --version-file version_info.txt --add-data "LICENSE;." --add-data "THIRD_PARTY_NOTICES;." --add-data "assets/checkbox-tick.png;assets" --icon assets/prosnip-bob.ico src/main.py
if errorlevel 1 goto :failed
call :maybe_pause
exit /b 0
:failed
call :maybe_pause
exit /b 1
:maybe_pause
if defined NOPAUSE exit /b 0
echo %CMDCMDLINE% | find /I "/c" >nul
if not errorlevel 1 pause
exit /b 0
