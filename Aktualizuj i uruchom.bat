@echo off
rem Update from GitHub, then start the board.
title DartSense - aktualizacja
cd /d "%~dp0"
echo Pobieranie nowej wersji...
git pull
if errorlevel 1 (
  echo.
  echo Aktualizacja nie powiodla sie - zrob zdjecie tego okna i wyslij je.
  pause
  exit /b 1
)
echo.
call "Uruchom tarcze.bat"
