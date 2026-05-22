@echo off
setlocal EnableExtensions
echo.
echo Removing containers with names containing "team" (images are preserved)...

REM Change to this script's directory (repo root)
cd /d "%~dp0"

set "FOUND="
for /f "delims=" %%A in ('docker ps -aq --filter "name=team"') do (
    set "FOUND=1"
    echo Removing container ID %%A
    docker rm -f %%A >nul 2>&1 || echo Failed to remove container %%A
)

if not defined FOUND (
    echo No team containers found.
)

echo.
echo Done.
endlocal
