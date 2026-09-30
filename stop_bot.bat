@echo off
setlocal
echo Stoppen van WerkZoeker processen...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('WerkZoeker proces ' + $_.ProcessId + ' gestopt.') }"
echo Gereed.
pause
