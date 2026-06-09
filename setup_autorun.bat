@echo off
echo ========================================
echo   Mars Chat - Setup Auto-Run
echo ========================================
echo.

REM Get the path to MarsChat.exe
set "EXE_PATH=%~dp0dist\MarsChat.exe"

if not exist "%EXE_PATH%" (
    echo [ERROR] MarsChat.exe not found at: %EXE_PATH%
    echo Please run build.bat first!
    pause
    exit /b 1
)

echo Setting up auto-run for: %EXE_PATH%
echo.

REM Create VBS launcher (hidden window)
echo Set WshShell = CreateObject("WScript.Shell") > "%~dp0marschat_launcher.vbs"
echo WshShell.Run """%EXE_PATH%""", 0, False >> "%~dp0marschat_launcher.vbs"

REM Copy shortcut to Startup folder
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

REM Create shortcut using PowerShell
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTUP%\MarsChat.lnk'); $s.TargetPath = '%~dp0marschat_launcher.vbs'; $s.WorkingDirectory = '%~dp0dist'; $s.Description = 'Mars Chat Server'; $s.Save()"

echo [OK] Auto-run shortcut created in Startup folder
echo [OK] Mars Chat will start automatically when Windows boots
echo.
echo To remove auto-run, delete: %STARTUP%\MarsChat.lnk
echo.
pause
