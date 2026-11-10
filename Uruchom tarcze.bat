@echo off
rem Start the board: double-click. Reachable from other devices on the network.
title DartSense - tarcza
cd /d "%~dp0"
echo Adres tarczy w sieci (wpisz w przegladarce na innym urzadzeniu, z :8000 na koncu):
ipconfig | findstr /c:"IPv4"
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start.ps1 -Lan
echo.
echo Tarcza zatrzymana. Nacisnij dowolny klawisz, aby zamknac okno.
pause >nul
