@echo off
setlocal EnableDelayedExpansion

rem Start the hackathon platform using organizer-stack/docker-compose.yml
rem Usage: start-platform.bat [TEAM_COUNT] [--build]
rem TEAM_COUNT means how many teams to pre-register automatically.
rem Default TEAM_COUNT is 0 (launch with no registered teams).
set "ROOT_DIR=%~dp0"
set "STACK_DIR=%ROOT_DIR%organizer-stack"
set "TEAM_COUNT=%~1"
set "BUILD_FLAG=%~2"
set "FORCE_BUILD=0"
set "PULL_UPDATES=0"

if "%TEAM_COUNT%"=="" set "TEAM_COUNT=0"

if /I "%TEAM_COUNT%"=="--build" (
  set "TEAM_COUNT=0"
  set "FORCE_BUILD=1"
)

if /I "%BUILD_FLAG%"=="--build" set "FORCE_BUILD=1"

if /I "%TEAM_COUNT%"=="--pull" (
  set "TEAM_COUNT=0"
  set "PULL_UPDATES=1"
)

if /I "%BUILD_FLAG%"=="--pull" set "PULL_UPDATES=1"

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

docker info >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] Docker engine is not running.
  echo         Start Docker Desktop, wait until it is ready, then run again.
  exit /b 1
)

pushd "%STACK_DIR%" || exit /b 1

set "SERVICE_LIST=orchestrator admin-dashboard tournament-display"
for /L %%I in (1,1,10) do (
  set "SERVICE_LIST=!SERVICE_LIST! team%%I-web team%%I-api team%%I-file team%%I-db team%%I-proxy team%%I-ide"
)

set "TEAM_COUNT=%TEAM_COUNT%"

if "%PULL_UPDATES%"=="1" (
  echo Checking Docker registry for image updates...
  call %COMPOSE_CMD% pull !SERVICE_LIST!
)

echo Starting platform from "%STACK_DIR%" with %TEAM_COUNT% team(s)...
set "RC=1"
if "%FORCE_BUILD%"=="1" (
  echo Build mode: enabled (forcing image rebuild)
  for /L %%A in (1,1,3) do (
    echo Startup attempt %%A/3...
    call %COMPOSE_CMD% up -d --build !SERVICE_LIST!
    set "RC=!ERRORLEVEL!"
    if "!RC!"=="0" goto :startup_done

    echo [WARN] docker compose up failed on attempt %%A with code !RC!.
    docker info >nul 2>&1
    if !errorlevel! neq 0 (
      echo [WARN] Docker engine is temporarily unavailable.
    )

    if %%A LSS 3 (
      echo [WARN] Retrying in 3 seconds...
      timeout /t 3 /nobreak >nul
    )
  )
) else (
  echo Build mode: stable reuse, no recreate unless missing
  echo Startup step 1/2: create only missing containers...
  call %COMPOSE_CMD% create --no-recreate --no-build !SERVICE_LIST!
  set "RC=!ERRORLEVEL!"
  if not "!RC!"=="0" goto :startup_done

  echo Startup step 2/2: start existing containers...
  call %COMPOSE_CMD% start !SERVICE_LIST!
  set "RC=!ERRORLEVEL!"
)

:startup_done

if not "%RC%"=="0" (
  echo.
  echo [ERROR] Failed to start platform. Exit code: %RC%
  popd
  exit /b %RC%
)

echo.
echo Waiting for orchestrator API to become ready...
set "ORCH_READY=0"
set /A ORCH_TRIES=0
:wait_orchestrator
set /A ORCH_TRIES+=1
curl -s -f "http://localhost:9000/current" >nul 2>&1
if !errorlevel! EQU 0 set "ORCH_READY=1"
if "%ORCH_READY%"=="1" goto :orchestrator_ready
if %ORCH_TRIES% LSS 30 (
  timeout /t 1 /nobreak >nul
  goto :wait_orchestrator
)

echo [WARN] Orchestrator API did not become ready in time.
echo [WARN] Teams were started but not auto-registered.
goto :post_registration

:orchestrator_ready
if %TEAM_COUNT% LEQ 0 (
  echo Started with no registered teams.
  echo Add teams from Admin UI one by one.
  goto :post_registration
)

echo Registering %TEAM_COUNT% team(s) in orchestrator...
set "REGISTERED=0"
set /A TEAM_IDX=1

:register_next_team
if !TEAM_IDX! GTR %TEAM_COUNT% goto :register_done
set /A PROXY_PORT=9099+!TEAM_IDX!
set /A IDE_PORT=8099+!TEAM_IDX!
curl -s -f -X POST "http://localhost:9000/register" -H "Content-Type: application/json" -d "{\"team_name\":\"Team !TEAM_IDX!\",\"ip\":\"team!TEAM_IDX!-proxy\",\"team_id\":!TEAM_IDX!,\"proxy_port\":!PROXY_PORT!,\"ide_port\":!IDE_PORT!}" >nul 2>&1
if !errorlevel! EQU 0 (
  set /A REGISTERED+=1
) else (
  echo [WARN] Could not register Team !TEAM_IDX! (team!TEAM_IDX!-proxy)
)
set /A TEAM_IDX+=1
goto :register_next_team

:register_done
echo Teams registered:   !REGISTERED!/%TEAM_COUNT%

:post_registration

echo.
echo Platform started successfully.
echo Team services ready: 10
echo Teams pre-registered: %TEAM_COUNT%
echo Admin dashboard:    http://localhost:4000
echo Tournament display: http://localhost:5000
echo Orchestrator API:   http://localhost:9000
echo.
echo Compose services:
call %COMPOSE_CMD% ps
echo.
echo Running Docker containers:
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo.
echo To check status:
echo   cd /d "%STACK_DIR%"
echo   %COMPOSE_CMD% ps
echo.
echo To pre-register all 10 teams at startup:
echo   %~nx0 10
echo.
echo To force rebuild images:
echo   %~nx0 10 --build
echo.
echo To check for registry image updates before startup:
echo   %~nx0 10 --pull

popd
exit /b 0
