@echo off
setlocal
set "root=%~dp0"
if "%~1"=="" (
    echo Put a 2048x1024 BC1 DDS with 12 mips in a folder named for the court, such as s272.
    echo Drag the DDS onto this file. Then enable the new Full Court mod in the launcher.
    pause
    exit /b 1
)
set "game=%root%port\out\vanilla-game"
if exist "%root%game\assets.json" set "game=%root%game"
if exist "%root%assets.json" set "game=%root%."
"%root%ch2k8_tools.exe" build-full-floor "%game%" "%~f1" "%root%mods"
if errorlevel 1 (
    echo Court mod build failed. See the message above.
    pause
    exit /b 1
)
echo Open Mods in the launcher and select the new Full Court version.
pause
