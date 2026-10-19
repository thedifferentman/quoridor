@echo off
cd /d "%~dp0"
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --reload --app-dir backend
