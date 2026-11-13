@echo off
REM Creates the daily 8:05am posting task. Run once after restoring.
schtasks /create /f /tn "AscendInstagramDailyPublish" /tr "\"%~dp0run_daily_publish.bat\"" /sc daily /st 08:05
pause
