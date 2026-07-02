@echo off
setlocal EnableExtensions EnableDelayedExpansion

title FH6 Road Finder Consolidated

set "ROOT=%~dp0"
set "INPUT_DIR=%ROOT%input"
set "OUTPUT_DIR=%ROOT%output"
set "TOOLS_DIR=%ROOT%tools"
set "SCRIPT=%TOOLS_DIR%\fh6_road_finder.py"
set "VENV_DIR=%ROOT%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

echo.
echo ============================================================
echo  FH6 Road Finder - consolidated launcher
echo ============================================================
echo.

if not exist "%INPUT_DIR%" mkdir "%INPUT_DIR%"
if errorlevel 1 goto mkdir_error
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
if errorlevel 1 goto mkdir_error
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"
if errorlevel 1 goto mkdir_error

if not exist "%SCRIPT%" (
    echo ERROR: Could not find:
    echo   "%SCRIPT%"
    echo.
    echo Make sure this BAT file is still next to the tools folder.
    goto end_error
)

echo Looking for Python...
set "PYTHON_CMD="

py -3 --version >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
    python --version >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    python3 --version >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python3"
)

if not defined PYTHON_CMD (
    echo.
    echo ERROR: Python was not found.
    echo.
    echo Install Python 3 from https://www.python.org/downloads/windows/
    echo During install, enable "Add python.exe to PATH".
    echo Then run this BAT file again.
    goto end_error
)

echo Found Python: %PYTHON_CMD%
echo.

if not exist "%VENV_PY%" (
    echo Creating local virtual environment:
    echo   "%VENV_DIR%"
    call %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to create the local .venv folder.
        goto end_error
    )
) else (
    echo Using existing local virtual environment.
)

echo.
echo Installing/updating required packages inside .venv...
echo   pillow
echo   numpy
echo   opencv-python
echo.
"%VENV_PY%" -m pip install --upgrade pillow numpy opencv-python
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install Python dependencies.
    echo Check your internet connection, then run this BAT file again.
    goto end_error
)

set "HAS_IMAGE=0"
set "HAS_JPEG=0"
for %%f in ("%INPUT_DIR%\*.png") do if exist "%%~f" set "HAS_IMAGE=1"
for %%f in ("%INPUT_DIR%\*.jpg") do if exist "%%~f" set "HAS_IMAGE=1" & set "HAS_JPEG=1"
for %%f in ("%INPUT_DIR%\*.jpeg") do if exist "%%~f" set "HAS_IMAGE=1" & set "HAS_JPEG=1"
for %%f in ("%INPUT_DIR%\*.bmp") do if exist "%%~f" set "HAS_IMAGE=1"
for %%f in ("%INPUT_DIR%\*.tif") do if exist "%%~f" set "HAS_IMAGE=1"
for %%f in ("%INPUT_DIR%\*.tiff") do if exist "%%~f" set "HAS_IMAGE=1"

if "%HAS_IMAGE%"=="0" (
    echo.
    echo WARNING: No supported image files found in:
    echo   "%INPUT_DIR%"
    echo.
    echo Supported: PNG - best, JPG/JPEG, BMP, TIF/TIFF
    goto end_ok
)

if "%HAS_JPEG%"=="1" (
    echo.
    echo JPEG files detected.
    echo PNG is still best, but this consolidated version can process JPEG.
    echo For JPEG screenshots, option 4 ^(tolerance 5^) is often a better first pass.
)

echo.
echo ============================================================
echo  Tolerance menu
echo ============================================================
echo.
echo  1. Ultra strict only, tolerance 0
echo  2. Strict only, tolerance 1
echo  3. Normal only, tolerance 2
echo  4. Loose only, tolerance 5  ^(recommended for JPEG screenshots^)
echo  5. Very loose only, tolerance 8
echo  6. Run ultra strict + strict + normal  ^(recommended for real PNG screenshots^)
echo  7. Run all modes
echo  8. Custom tolerance
echo.
if "%HAS_JPEG%"=="1" (
    echo Press one number key. Recommended for JPEG: 4
) else (
    echo Press one number key. Recommended for PNG: 6
)
choice /C 12345678 /N /M "Choose option: "
set "MENU_CHOICE=%ERRORLEVEL%"

set "TOLERANCES="
if "%MENU_CHOICE%"=="1" set "TOLERANCES=0"
if "%MENU_CHOICE%"=="2" set "TOLERANCES=1"
if "%MENU_CHOICE%"=="3" set "TOLERANCES=2"
if "%MENU_CHOICE%"=="4" set "TOLERANCES=5"
if "%MENU_CHOICE%"=="5" set "TOLERANCES=8"
if "%MENU_CHOICE%"=="6" set "TOLERANCES=0,1,2"
if "%MENU_CHOICE%"=="7" set "TOLERANCES=0,1,2,5,8"
if "%MENU_CHOICE%"=="8" (
    set "CUSTOM_TOLERANCE="
    set /p "CUSTOM_TOLERANCE=Enter comma-separated tolerances, such as 3 or 3,5,8: "
    set "TOLERANCES=!CUSTOM_TOLERANCE!"
)

if not defined TOLERANCES (
    echo.
    echo ERROR: Invalid menu choice.
    goto end_error
)

echo.
echo ============================================================
echo  Running detector
echo ============================================================
echo.
echo Input folder:
echo   "%INPUT_DIR%"
echo Output folder:
echo   "%OUTPUT_DIR%"
echo Tolerances:
echo   %TOLERANCES%
echo.

"%VENV_PY%" "%SCRIPT%" ^
    --input "%INPUT_DIR%" ^
    --output "%OUTPUT_DIR%" ^
    --target-rgb 128,128,128 ^
    --tolerances "%TOLERANCES%" ^
    --min-cluster-size 8 ^
    --highlight-color 255,0,0 ^
    --overlay-alpha 0.85 ^
    --distance-mode channel

if errorlevel 1 (
    echo.
    echo ERROR: The detector stopped because of an error.
    goto end_error
)

echo.
echo ============================================================
echo  Done
echo ============================================================
echo.
echo Open this first:
echo   "%OUTPUT_DIR%\report.html"
echo.
echo Then check the *_overlay.png files for red highlighted areas.
if exist "%OUTPUT_DIR%\report.html" (
    echo.
    echo Opening report in your browser...
    start "" "%OUTPUT_DIR%\report.html"
)
goto end_ok

:mkdir_error
echo.
echo ERROR: Could not create input/output/tools folders.
goto end_error

:end_error
echo.
pause
exit /b 1

:end_ok
echo.
pause
exit /b 0
