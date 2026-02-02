# Image Handler Test Suite

This test suite validates the MLS `image_handler` module using real camera images from the `mhi_cam` repository.

## Overview

The test suite processes JPG frames from `mhi_cam/output_images/` through the MLS `image_handler` and produces:

1. **Labelled Frames** - Original images with ion detection overlays (circles, crosshairs, parameters)
2. **Ion Data JSON** - Position and fit parameters for each detected ion
3. **Test Report** - Statistics on processing success rate, timing, ion counts
4. **Visual Comparison** - HTML page showing original vs labelled side-by-side

## Prerequisites

```bash
# Install dependencies
pip install opencv-python numpy scipy
```

## Directory Structure

```
MLS/tests/
├── test_image_handler_with_mhi_cam.py    # Main test program
├── visualize_image_handler_results.py    # Visual comparison tool
├── run_image_handler_test.bat            # Windows batch runner
├── IMAGE_HANDLER_TEST_README.md          # This file
└── output/
    └── image_handler_test/               # Test outputs
        ├── labelled_frames/              # Processed images
        ├── ion_data/                     # JSON files
        ├── report.txt                    # Text summary
        ├── report.json                   # Machine-readable summary
        └── comparison.html               # Visual comparison page
```

## Usage

### Quick Start (Windows)

```bash
cd MLS\tests
run_image_handler_test.bat
```

### Command Line

```bash
# Run with default settings (all images from mhi_cam/output_images)
python test_image_handler_with_mhi_cam.py

# Limit to 50 images
python test_image_handler_with_mhi_cam.py --max-images 50

# Custom ROI (Region of Interest)
python test_image_handler_with_mhi_cam.py --roi 200 250 400 500

# Custom paths
python test_image_handler_with_mhi_cam.py \
    --mhi-cam-path "D:/mhi_cam/output_images" \
    --output-path "D:/test_output"
```

### Visualize Results

```bash
# Show side-by-side comparison with auto-advance
python visualize_image_handler_results.py

# Slow down to 1 second per image
python visualize_image_handler_results.py --delay 1000
```

## Test Output Format

### Labelled Frame Naming
```
{original_name}_labelled.jpg

Example: 2024_08_09_4_frame_0_labelled.jpg
```

### Ion Data JSON Format
```json
{
    "timestamp": "2026-02-02T14:30:15.123456",
    "frame_number": 0,
    "ions": {
        "ion_1": {
            "pos_x": 320.5,
            "pos_y": 240.3,
            "sig_x": 15.2,
            "R_y": 8.7
        }
    },
    "fit_quality": 0.95,
    "processing_time_ms": 45.2
}
```

### Report Format (report.txt)
```
============================================================
Image Handler Test Report
============================================================
Test Date: 2026-02-02T14:30:15
ROI: (180, 220, 425, 495)

Summary Statistics:
  Total images: 500
  Successful: 498
  Failed: 2
  Success rate: 99.6%
  Total ions detected: 523
  Avg processing time: 42.3ms
  Total time: 21.1s
```

## ROI (Region of Interest) Configuration

The ROI defines the sub-region of the image where ions are detected:

```bash
--roi X_START X_FINISH Y_START Y_FINISH
```

Default: `(180, 220, 425, 495)`

- For full-frame detection: `--roi 0 1024 0 1024`
- For specific area: `--roi 200 300 400 500`

## Interpreting Results

### Success Criteria
- **Success Rate > 90%**: Image handler is working correctly
- **Success Rate 70-90%**: May need ROI adjustment or parameter tuning
- **Success Rate < 70%**: Check image format, OpenCV installation

### Ion Detection Quality
- **Good**: Consistent ion positions across frames, fit_quality > 0.8
- **Poor**: Jittery positions, low fit_quality, check threshold_sigma

### Performance
- **Fast**: < 50ms per frame
- **Normal**: 50-100ms per frame
- **Slow**: > 100ms per frame (check ROI size)

## Troubleshooting

### "No test images found"
```bash
# Check mhi_cam path
ls ../../mhi_cam/output_images/*.jpg

# If not found, specify custom path
python test_image_handler_with_mhi_cam.py --mhi-cam-path "C:/path/to/images"
```

### "Could not read image"
- Verify OpenCV is installed: `pip install opencv-python`
- Check image files are valid JPGs

### "No ions detected"
- Try adjusting ROI: `--roi 0 1024 0 1024` for full frame
- Check images actually contain ions (bright spots)

### Visualization window too large
```python
# In visualize_image_handler_results.py, adjust:
max_width = 1600
max_height = 900
```

## Integration with CI/CD

```bash
# Run tests with exit code check
python test_image_handler_with_mhi_cam.py --max-images 100
if [ $? -eq 0 ]; then
    echo "Tests PASSED"
else
    echo "Tests FAILED"
    exit 1
fi
```

## Next Steps

After successful testing:
1. Copy `image_handler.py` to production server
2. Configure paths in `config/settings.yaml`
3. Start image handler as background service
4. Verify ion data appears in `E:/Data/ion_data/`

## Support

For issues with:
- **Test suite**: Check `report.txt` and `report.json`
- **Image handler**: See `server/cam/README.md`
- **mhi_cam images**: Verify mhi_cam repository is at same level as MLS
