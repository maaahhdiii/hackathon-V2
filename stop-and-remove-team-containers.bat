@echo off
setlocal
echo.
echo Removing containers with names containing "team" (images are preserved)...

REM Change to this script's directory (repo root)
cd /d "%~dp0"

for /f "usebackq tokens=1,2" %%A in (`docker ps -a --format "{{.ID}} {{.Names}}" ^| findstr /i "team"`) do (
    echo Removing container %%B (ID %%A)
    docker rm -f %%A >nul 2>&1 || echo Failed to remove container %%B
)

echo.
echo Done.
endlocal
