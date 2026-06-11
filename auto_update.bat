@echo off
REM ============================================================
REM  Anime catalog quarterly auto-update (run by Task Scheduler)
REM  Fires on 1/1, 4/1, 7/1, 10/1: scrape --update then git push
REM  Can also be run manually by double-clicking this file.
REM ============================================================
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PY="C:\Users\nagi3\AppData\Local\Programs\Python\Python310\python.exe"
cd /d "D:\Claude\Everything-claude-code\anime-list"

echo ============================================================>> auto_update.log
echo [%date% %time%] update start>> auto_update.log

%PY% scrape_anime.py --update >> auto_update.log 2>&1

git add anime-data.js >> auto_update.log 2>&1
git commit -m "chore: quarterly auto-update" >> auto_update.log 2>&1
git push origin main >> auto_update.log 2>&1

echo [%date% %time%] done>> auto_update.log
