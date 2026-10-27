@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Dang cai dat lan dau...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
.venv\Scripts\python.exe -m maker %*
pause
