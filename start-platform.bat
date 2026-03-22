@echo off
setlocal EnableDelayedExpansion

rem Start the hackathon platform using organizer-stack/docker-compose.yml
rem Usage: start-platform.bat [TEAM_COUNT]
rem TEAM_COUNT means how many teams to pre-register automatically.
rem Default TEAM_COUNT is 0 (launch with no registered teams).
set "ROOT_DIR=%~dp0"
set "STACK_DIR=%ROOT_DIR%organizer-stack"
set "TEAM_COUNT=%~1"

if "%TEAM_COUNT%"=="" set "TEAM_COUNT=0"

echo %TEAM_COUNT%| findstr /R "^[0-9][0-9]*$" >nul
if errorlevel 1 (
  echo [ERROR] TEAM_COUNT must be a number from 0 to 10.
  exit /b 1
)

if %TEAM_COUNT% GTR 10 (
  echo [ERROR] TEAM_COUNT cannot be greater than 10.
  exit /b 1
)

if not exist "%STACK_DIR%\docker-compose.yml" (
  echo [ERROR] Could not find docker-compose.yml in:
  echo         "%STACK_DIR%"
  exit /b 1
)

rem Prefer Docker Compose v2, then fallback to docker-compose v1.
docker compose version >nul 2>&1
if %errorlevel%==0 (
  set "COMPOSE_CMD=docker compose"
) else (
  docker-compose version >nul 2>&1
  if %errorlevel%==0 (
    set "COMPOSE_CMD=docker-compose"
  ) else (
    echo [ERROR] Docker Compose is not available.
    echo         Install Docker Desktop and try again.
    exit /b 1
  )
)

pushd "%STACK_DIR%" || exit /b 1

set "SERVICE_LIST=orchestrator admin-dashboard tournament-display"
for /L %%I in (1,1,10) do (
  set "SERVICE_LIST=!SERVICE_LIST! team%%I-web team%%I-api team%%I-file team%%I-db team%%I-proxy team%%I-ide"
)

set "TEAM_COUNT=%TEAM_COUNT%"

echo Starting platform from "%STACK_DIR%" with %TEAM_COUNT% team(s)...
call %COMPOSE_CMD% up -d --build !SERVICE_LIST!
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo [ERROR] Failed to start platform. Exit code: %RC%
  popd
  exit /b %RC%
)

echo.
echo Waiting for orchestrator API to become ready...
set "ORCH_READY=0"
for /L %%I in (1,1,30) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod -Method Get -Uri 'http://localhost:9000/current' -TimeoutSec 2; if($null -ne $r){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
  if !errorlevel! EQU 0 (
    set "ORCH_READY=1"
  )
  if "!ORCH_READY!"=="0" timeout /t 1 /nobreak >nul
)
if "%ORCH_READY%"=="1" (
  if %TEAM_COUNT% GTR 0 (
    echo Registering %TEAM_COUNT% team(s) in orchestrator...
    set "REGISTERED=0"
    for /L %%I in (1,1,%TEAM_COUNT%) do (
      powershell -NoProfile -ExecutionPolicy Bypass -Command "$body=ConvertTo-Json @{team_name=('Team %%I');ip=('team%%I-proxy');team_id=%%I;proxy_port=(9100 + (%%I - 1));ide_port=(8100 + (%%I - 1))}; try { $r=Invoke-RestMethod -Method Post -Uri 'http://localhost:9000/register' -ContentType 'application/json' -Body $body -TimeoutSec 5; if($r.ok){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
      if !errorlevel!==0 (
        set /A REGISTERED+=1
      ) else (
        echo [WARN] Could not register Team %%I (team%%I-proxy)
      )
    )
    echo Teams registered:   !REGISTERED!/%TEAM_COUNT%
  ) else (
    echo Started with no registered teams.
    echo Add teams from Admin UI one by one.
  )
) else (
  echo [WARN] Orchestrator API did not become ready in time.
  echo [WARN] Teams were started but not auto-registered.
)

echo.
echo Platform started successfully.
echo Team services ready: 10
echo Teams pre-registered: %TEAM_COUNT%
echo Admin dashboard:    http://localhost:4000
echo Tournament display: http://localhost:5000
echo Orchestrator API:   http://localhost:9000
echo.
echo To check status:
echo   cd /d "%STACK_DIR%"
echo   %COMPOSE_CMD% ps
echo.
echo To pre-register all 10 teams at startup:
echo   %~nx0 10

popd
exit /b 0
