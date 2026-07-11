@echo off
set LOG=C:\Users\Arghyadeep\Desktop\AI video maker\deploy\tunnel\tunnel.log
:loop
echo. >> "%LOG%"
echo === restart %date% %time% === >> "%LOG%"
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000 >> "%LOG%" 2>&1
timeout /t 5 /nobreak >nul
goto loop
