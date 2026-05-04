@echo off
REM B2Have Career Intelligence — Daily Pipeline Runner
REM Run by Windows Task Scheduler at 8:00 AM daily

cd /d "C:\Users\Inspiron\Documents\career-intelligence-system"

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run the pipeline
python main.py

REM Log completion
echo %date% %time% — Pipeline run complete >> data\logs\task_scheduler.log
