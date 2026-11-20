@echo off
rem New launcher: needs Python (pythonw). Falls back to the classic launcher if it is missing.
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw -B "%~dp0launcher\host.py"
  exit /b 0
)
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 -B "%~dp0launcher\host.py"
  exit /b 0
)
start "" "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0tools\start_launcher.ps1"
