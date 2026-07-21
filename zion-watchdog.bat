@echo off
rem Paznicul Zion Stream: tine aplicatia mereu pornita.
rem Daca aplicatia se inchide (update sau eroare), o reporneste in ~4 secunde.
cd /d "%~dp0"
:loop
if exist "ZionStream-new.exe" (
  move /y "ZionStream-new.exe" "ZionStream.exe" >nul 2>&1
)
if exist "ZionStream.exe" (
  ZionStream.exe
) else (
  timeout /t 10 /nobreak >nul
)
timeout /t 4 /nobreak >nul
goto loop
