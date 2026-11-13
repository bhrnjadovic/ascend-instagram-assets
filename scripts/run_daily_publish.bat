@echo off
cd /d "%~dp0"
echo. >> daily_publish.log
echo ===== %date% %time% ===== >> daily_publish.log

REM Sync any new/updated slide images to GitHub first. Instagram downloads each
REM slide from the public GitHub copy (PUBLIC_IMAGE_BASE_URL), so a re-rendered
REM cover only takes effect once it has been pushed there.
pushd ..
git add 03_generated_posts >> scripts\daily_publish.log 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git commit -q -m "Auto-sync generated post images" >> scripts\daily_publish.log 2>&1
    git pull -q --rebase --autostash origin main >> scripts\daily_publish.log 2>&1
    git push -q origin HEAD:main >> scripts\daily_publish.log 2>&1
    if errorlevel 1 (echo WARNING: git push failed - Instagram may still fetch old images >> scripts\daily_publish.log) else (echo Image sync pushed to GitHub. >> scripts\daily_publish.log)
)
popd

py -3 instagram_publish.py --publish-due >> daily_publish.log 2>&1
