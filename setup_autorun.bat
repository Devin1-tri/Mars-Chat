@echo off
echo ========================================
echo   Mars Chat - Setup Auto-Run
echo ========================================
echo.

set "EXE_PATH=%~dp0dist\MarsChat.exe"

if not exist "%EXE_PATH%" (
    echo [ERROR] MarsChat.exe not found at: %EXE_PATH%
    echo Please run build.bat first!
    pause
    exit /b 1
)

echo Setting up auto-run for: %EXE_PATH%
echo.

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTUP%\MarsChat.lnk'); $s.TargetPath = '%EXE_PATH%'; $s.WorkingDirectory = '%~dp0dist'; $s.Description = 'Mars Chat Server'; $s.Save()"

echo [OK] Auto-run shortcut created in Startup folder
echo [OK] Mars Chat will start silently when Windows boots
echo.
echo To remove auto-run, delete: %STARTUP%\MarsChat.lnk
echo.
pause
