@echo off
title Zion Stream - instalare
cd /d "%~dp0"

echo [1/6] Verific daca Python e instalat...
where py >nul 2>&1 && goto :havepython
echo    Python lipseste - il descarc si il instalez automat (dureaza 2-3 minute)...
curl -L -o "%TEMP%\python-setup.exe" https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
if not exist "%TEMP%\python-setup.exe" powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile \"$env:TEMP\python-setup.exe\""
if not exist "%TEMP%\python-setup.exe" (
  echo    EROARE: nu am putut descarca Python. Instaleaza-l manual de pe python.org
  echo    cu optiunea "Add python.exe to PATH" bifata, apoi ruleaza din nou acest fisier.
  pause
  exit /b 1
)
echo    Instalez Python - asteapta, fara ferestre...
"%TEMP%\python-setup.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1 InstallLauncherAllUsers=1
where py >nul 2>&1 || (
  echo    EROARE: instalarea Python a esuat. Ruleaza acest fisier ca Administrator,
  echo    sau instaleaza Python manual de pe python.org si ruleaza din nou.
  pause
  exit /b 1
)
echo    Python instalat cu succes.
:havepython
set PY=py

echo [2/6] Instalez componentele (prima data dureaza putin)...
%PY% -m pip install --quiet --upgrade yt-dlp flask requests

echo [3/6] Aleg lansatorul fara fereastra...
set LAUNCHER=pyw.exe
where pyw.exe >nul 2>&1 || set LAUNCHER=pythonw.exe

echo [4/6] Pun serverul la pornirea Windows-ului...
set VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ZionStream.vbs
(
  echo Set ws = CreateObject("WScript.Shell"^)
  echo ws.Run "%LAUNCHER% ""%~dp0zion-server.py""", 0, False
) > "%VBS%"

echo [5/6] Deschid portul in firewall - doar pe retele private (daca am drepturi)...
netsh advfirewall firewall delete rule name="Zion Stream" >nul 2>&1
netsh advfirewall firewall add rule name="Zion Stream" dir=in action=allow protocol=TCP localport=8321 profile=private,domain >nul 2>&1 || echo    (nu am drepturi de admin - daca telefonul nu se conecteaza, ruleaza acest fisier ca Administrator)

echo [6/6] Creez scurtatura "Zion Stream" pe Desktop...
(
  echo [InternetShortcut]
  echo URL=http://localhost:8321
  echo IconIndex=23
  echo IconFile=%%SystemRoot%%\System32\SHELL32.dll
) > "%USERPROFILE%\Desktop\Zion Stream.url"

echo.
echo Pornesc serverul acum, pe fundal...
wscript "%VBS%"
timeout /t 3 /nobreak >nul

echo.
echo ================================================
echo  GATA! Serverul ruleaza si porneste singur
echo  odata cu Windows-ul.
echo.
echo  Pe PC: dublu-click pe "Zion Stream" de pe Desktop.
for /f "tokens=2 delims=: " %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  echo  Pe telefon, optional:  http://%%a:8321
  goto :done
)
:done
echo ================================================
start http://localhost:8321
echo.
pause
