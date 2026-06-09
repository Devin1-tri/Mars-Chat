@echo off
echo ========================================
echo   Mars Chat - Build EXE
echo ========================================
echo.

REM Install dependencies
pip install -r requirements.txt
pip install pyinstaller

REM Build EXE
pyinstaller --clean marschat.spec

echo.
echo ========================================
echo   Build complete!
echo   EXE: dist\MarsChat.exe
echo ========================================
pause
