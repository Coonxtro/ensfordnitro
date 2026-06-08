@echo off
cls
if not exist "venv\Scripts\activate.bat" (
  echo ERROR: venv not found. Run setup.bat first.
  exit /b 1
)
call "venv\Scripts\activate.bat"
python bot.py %*
if errorlevel 1 (
  echo Application failed with exit code %errorlevel%
  exit /b %errorlevel%
)
exit /b 0
