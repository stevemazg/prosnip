@echo off
pyinstaller --noconfirm --clean --onefile --windowed --noupx --name ProSnip-Bob --exclude-module tkinter src/main.py
pause
