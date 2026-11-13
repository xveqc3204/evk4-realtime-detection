@echo off
setlocal EnableExtensions
rem Windows double-click launcher. The control window opens without a camera.
cd /d "%~dp0"
if defined EBS_GUI_PYTHON (
    if exist "%EBS_GUI_PYTHON%" (
        "%EBS_GUI_PYTHON%" -c "import sys, tkinter; assert sys.version_info >= (3,10)" >nul 2>&1
        if not errorlevel 1 (
            "%EBS_GUI_PYTHON%" "%~dp0rotor_lab\operator_gui.py"
            goto :done
        )
    )
)
for %%P in ("%~dp0rotor_lab\.venv\Scripts\python.exe" "%~dp0.venv\Scripts\python.exe") do (
    if exist "%%~fP" (
        "%%~fP" -c "import sys, tkinter; assert sys.version_info >= (3,10)" >nul 2>&1
        if not errorlevel 1 (
            "%%~fP" "%~dp0rotor_lab\operator_gui.py"
            goto :done
        )
    )
)
where py >nul 2>&1
if not errorlevel 1 (
    py -3.10 -c "import tkinter" >nul 2>&1
    if not errorlevel 1 (
        py -3.10 "%~dp0rotor_lab\operator_gui.py"
        goto :done
    )
)
echo EBS GUI needs Python 3.10 64-bit with tkinter.
echo Install a Python.org Windows distribution, then try again.
echo Test: py -3.10 -m tkinter
echo No camera is needed to open the controls.
:done
echo.
echo EBS GUI exited. Press any key to close this window.
pause >nul
