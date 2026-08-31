@echo off
REM freeclaudio launcher (Windows)
REM Sobe o proxy e roda o Claude Code junto.
setlocal
set "SCRIPT_DIR=%~dp0"
set "PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%"
python -m freeclaudio %*
exit /b %ERRORLEVEL%
