@echo off
python scripts\write_version_info.py
if errorlevel 1 exit /b 1
pyinstaller --noconfirm --clean --onedir --windowed --noupx --name ProSnip-Bob --exclude-module tkinter --version-file version_info.txt --add-data "LICENSE;." --add-data "THIRD_PARTY_NOTICES;." src/main.py
pause
