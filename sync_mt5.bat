@echo off
set PYTHONUTF8=1
set PYTHONPATH=E:\FTMO-Bot\.venv312\Lib\site-packages
E:\tools\python312\python.exe E:\quantrigiaodich-web\journal_sync.py >> E:\quantrigiaodich-web\sync_log.txt 2>&1
echo exit %ERRORLEVEL% at %DATE% %TIME% >> E:\quantrigiaodich-web\sync_log.txt
