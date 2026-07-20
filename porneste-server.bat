@echo off
title Zion Stream Server
cd /d "%~dp0"

set PY=python
where py >nul 2>&1 && set PY=py

echo Instalez/actualizez componentele (prima data dureaza putin)...
%PY% -m pip install --quiet --upgrade yt-dlp flask requests
echo.
%PY% zion-server.py
pause
