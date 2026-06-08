@echo off
setlocal enabledelayedexpansion

:: verify python is available
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    exit /b 1
)

:: create venv if missing
if not exist "venv\Scripts\activate.bat" (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        exit /b 1
    )
)

:: activate venv
call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    exit /b 1
)

:: upgrade pip and install requirements
python -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: pip upgrade failed.
    exit /b 1
)
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    exit /b 1
)

cls
echo Setup complete. 
echo To activate venv: call venv\Scripts\activate.bat
echo To run your app: python main.py
endlocal
exit /b 0