@echo off
cd /d "C:\Users\Arghyadeep\Desktop\AI video maker\backend"
:loop
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "C:\Users\Arghyadeep\Desktop\AI video maker\deploy\tunnel\backend.log" 2>&1
echo %date% %time% backend exited, restarting in 5s >> "C:\Users\Arghyadeep\Desktop\AI video maker\deploy\tunnel\backend.log"
timeout /t 5 /nobreak >nul
goto loop
