@echo off
echo ========================================
echo   Building Hextech Draft
echo ========================================
echo.
pip install requests urllib3 psutil pywebview pyinstaller
echo.
echo Building EXE...
pyinstaller --onefile --windowed --name "HextechDraft" --icon "hextech_icon.ico" --clean hextech_auto_accept.py
echo.
echo ========================================
echo   DONE! EXE at: dist\HextechDraft.exe
echo ========================================
pause
