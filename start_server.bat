@echo off
cd /d "%~dp0server"
if not exist .venv\Scripts\python.exe (
  echo Criando ambiente virtual...
  py -m venv .venv
  call .venv\Scripts\activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
if not exist .env copy .env.example .env >nul
python -m uvicorn app:app --host 0.0.0.0 --port 8000
pause
