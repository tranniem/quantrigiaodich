@echo off
cd /d "%~dp0"
git add -A
git commit -m "Cap nhat app"
git push origin main
pause
