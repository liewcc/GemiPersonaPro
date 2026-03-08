@echo off
title GemiPersona
cd /d %~dp0

echo Starting Web Interface...
.venv\Scripts\python.exe -m streamlit run start.py

pause