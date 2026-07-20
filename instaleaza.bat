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

echo Pornire automata cu Windows...
> "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ZionStream.vbs" (
  echo Set ws = CreateObject("WScript.Shell"^)
  echo ws.Run """%DIR%\ZionStream.exe""", 0, False
)

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

echo Pornesc aplicatia...
wscript "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ZionStream.vbs"
timeout /t 3 /nobreak >nul
start http://localhost:8321

echo.
echo GATA! De acum: dublu-click pe "Zion Stream" de pe Desktop.
echo Aplicatia porneste singura cu Windows-ul si se actualizeaza singura.
pause
