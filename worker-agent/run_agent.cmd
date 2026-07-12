@echo off
cd /d "C:\Users\Arghyadeep\Desktop\AI video maker\worker-agent"
".venv\Scripts\python.exe" -m worker_agent --no-tray > "agent.log" 2>&1
