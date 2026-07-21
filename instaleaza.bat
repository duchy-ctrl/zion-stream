@echo off
title Zion Stream - instalare
set DIR=C:\ZionStream
mkdir "%DIR%" 2>nul

echo Descarc aplicatia (ultima versiune)...
curl -L -o "%DIR%\ZionStream.exe" https://github.com/duchy-ctrl/zion-stream/releases/latest/download/ZionStream.exe
if not exist "%DIR%\ZionStream.exe" (
  echo EROARE la descarcare. Verifica internetul si incearca din nou.
  pause
  exit /b 1
)

echo Pun paznicul (tine muzica mereu pornita, chiar si dupa update)...
> "%DIR%\zion-watchdog.bat" (
  echo @echo off
  echo cd /d "%%~dp0"
  echo :loop
  echo if exist "ZionStream-new.exe" move /y "ZionStream-new.exe" "ZionStream.exe" ^>nul 2^>^&1
  echo if exist "ZionStream.exe" ^(ZionStream.exe^) else ^(timeout /t 10 /nobreak ^>nul^)
  echo timeout /t 4 /nobreak ^>nul
  echo goto loop
)

echo Pornire automata cu Windows (prin paznic)...
> "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ZionStream.vbs" (
  echo Set ws = CreateObject("WScript.Shell"^)
  echo ws.Run """%DIR%\zion-watchdog.bat""", 0, False
)

echo Opresc eventuale instante vechi...
taskkill /f /im ZionStream.exe >nul 2>&1

echo Deschid portul in firewall...
netsh advfirewall firewall delete rule name="Zion Stream" >nul 2>&1
netsh advfirewall firewall add rule name="Zion Stream" dir=in action=allow protocol=TCP localport=8321 profile=private,domain >nul 2>&1

echo Scurtatura pe Desktop...
(
  echo [InternetShortcut]
  echo URL=http://localhost:8321
  echo IconIndex=23
  echo IconFile=%%SystemRoot%%\System32\SHELL32.dll
) > "%USERPROFILE%\Desktop\Zion Stream.url"

echo Pornesc aplicatia (prin paznic)...
wscript "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ZionStream.vbs"
timeout /t 4 /nobreak >nul
start http://localhost:8321

echo.
echo GATA! De acum: dublu-click pe "Zion Stream" de pe Desktop.
echo Aplicatia porneste singura cu Windows-ul, se repara singura daca se
echo inchide, si se actualizeaza singura. Muzica revine automat.
pause
