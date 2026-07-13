@echo off
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --edge-ip-version 4 --url http://localhost:8000 > "C:\Users\Arghyadeep\Desktop\AI video maker\deploy\tunnel\tunnel.log" 2>&1
