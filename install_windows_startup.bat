@echo off
setlocal
echo ============================================================
echo   WerkZoeker - Automatisch opstarten met Windows instellen
echo ============================================================
echo.

set SCRIPT_DIR=%~dp0
set VBS_TARGET=%SCRIPT_DIR%start_bot_background.vbs
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT_NAME=WerkZoekerBot.lnk

echo Script locatie: %VBS_TARGET%
echo Startup map:    %STARTUP_DIR%
echo.

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTUP_DIR%\%SHORTCUT_NAME%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS_TARGET%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.WindowStyle = 7; $s.Save()"

if %errorlevel% equ 0 (
    echo [OK] WerkZoeker is succesvol toegevoegd aan Windows Opstarten!
    echo Vanaf nu start de bot automatisch onzichtbaar op de achtergrond
    echo zodra u uw computer opstart of inlogt.
    echo.
) else (
    echo [FOUT] Kon snelkoppeling niet aanmaken.
)

pause
