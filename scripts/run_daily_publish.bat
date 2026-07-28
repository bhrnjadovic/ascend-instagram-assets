@echo off
cd /d "%~dp0"
echo. >> daily_publish.log
echo ===== %date% %time% ===== >> daily_publish.log
"C:\Users\bosan\AppData\Local\Python\pythoncore-3.14-64\python.exe" instagram_publish.py --publish-due >> daily_publish.log 2>&1
