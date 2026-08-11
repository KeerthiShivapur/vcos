@echo off
set DB_POOL_SIZE=50
set DB_MAX_OVERFLOW=30
cd /d D:\workspace\vcos\backend
D:\workspace\vcos\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8999 > D:\workspace\vcos\backend\uvicorn-4c.log 2> D:\workspace\vcos\backend\uvicorn-4c.err.log
