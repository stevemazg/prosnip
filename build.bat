@echo off
pyinstaller --noconfirm --clean --onedir --windowed --noupx --name ProSnip-Bob --exclude-module tkinter --collect-data imageio_ffmpeg --version-file version_info.txt src/main.py
pause
