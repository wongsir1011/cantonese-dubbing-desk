@echo off
rem ============================================================
rem  Cantonese Dubbing Desk - Windows launcher
rem  This file is intentionally pure ASCII. Do NOT add Chinese
rem  characters here: cmd.exe parses .bat files using the system
rem  code page (CP950 on Traditional Chinese Windows), so UTF-8
rem  Chinese would be mangled and executed as commands.
rem  All Chinese messages are printed by serve.py instead.
rem ============================================================

setlocal
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Cantonese Dubbing Desk

rem An elevated cmd window starts in C:\Windows\System32,
rem so always move to the folder holding this file.
cd /d "%~dp0"

if not exist "serve.py" goto noserver

set "PY="
where py >nul 2>nul
if %errorlevel%==0 set "PY=py"
if defined PY goto run

where python >nul 2>nul
if %errorlevel%==0 set "PY=python"
if defined PY goto run

where python3 >nul 2>nul
if %errorlevel%==0 set "PY=python3"
if defined PY goto run

goto nopython

:run
%PY% serve.py %*
goto done

:noserver
echo.
echo   ERROR: serve.py not found in this folder.
echo   Folder: %~dp0
echo.
echo   Put launch.bat, serve.py and index.html in the SAME folder.
echo.
pause
exit /b 1

:nopython
echo.
echo   ERROR: Python not found.
echo.
echo   Download it from https://www.python.org/downloads/
echo   During setup, tick "Add python.exe to PATH".
echo   Then close this window, open it again and retry.
echo.
pause
exit /b 1

:done
echo.
echo   Server stopped.
pause
