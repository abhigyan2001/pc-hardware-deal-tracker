@echo off
REM Wrapper for Windows Task Scheduler: pins the working directory and uses the
REM project venv, so the task does not depend on the scheduler's environment.
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py >> "data\tracker.log" 2>&1
