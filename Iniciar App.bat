@echo off
cd /d "%~dp0"
echo Iniciando Markowitz Pro Picks...
start "" python -m streamlit run app.py
