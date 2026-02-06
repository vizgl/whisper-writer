@echo off
cd /d D:\Tools\WhisperInput\whisper-writer
set PATH=venv\Lib\site-packages\nvidia\cudnn\bin;%PATH%
start "" venv\Scripts\pythonw.exe run.py
exit