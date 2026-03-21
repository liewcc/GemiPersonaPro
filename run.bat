@echo off
title GemiPersona
cd /d %~dp0

type sys_img\banner.txt

.venv\Scripts\python.exe -m streamlit run start.py

pause