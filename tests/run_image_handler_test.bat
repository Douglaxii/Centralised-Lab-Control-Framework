@echo off
REM Image Handler Test Runner
REM Tests the MLS image_handler using mhi_cam images

echo ==========================================
echo Image Handler Test - MLS
echo ==========================================
echo.

REM Check if we're in the right directory
if not exist "..\server\cam\image_handler.py" (
    echo ERROR: Please run this script from the MLS/tests directory
    exit /b 1
)

REM Set paths
set MHI_CAM_PATH=..\..\mhi_cam\output_images
set OUTPUT_PATH=output\image_handler_test

REM Check if mhi_cam images exist
if not exist "%MHI_CAM_PATH%" (
    echo ERROR: mhi_cam images not found at %MHI_CAM_PATH%
    echo Please ensure mhi_cam repository is at the same level as MLS
    exit /b 1
)

echo Configuration:
echo   mhi_cam images: %MHI_CAM_PATH%
echo   Output: %OUTPUT_PATH%
echo.

REM Create output directory
if not exist "%OUTPUT_PATH%" mkdir "%OUTPUT_PATH%"

REM Run the test
echo Running tests...
python test_image_handler_with_mhi_cam.py --mhi-cam-path "%MHI_CAM_PATH%" --output-path "%OUTPUT_PATH%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Tests completed with warnings or errors.
) else (
    echo.
    echo Tests completed successfully!
)

echo.
echo Output locations:
echo   Labelled frames: %OUTPUT_PATH%\labelled_frames\
echo   Ion data (JSON): %OUTPUT_PATH%\ion_data\
echo   Report: %OUTPUT_PATH%\report.txt
echo   HTML comparison: %OUTPUT_PATH%\comparison.html
echo.

pause
