# Image Handler Test Suite - Summary

## Created Files

| File | Size | Purpose |
|------|------|---------|
| `test_image_handler_with_mhi_cam.py` | 18.5 KB | Main test program - processes mhi_cam images |
| `visualize_image_handler_results.py` | 5.5 KB | Visual comparison tool - side-by-side display |
| `run_image_handler_test.bat` | 1.5 KB | Windows batch runner - one-click testing |
| `IMAGE_HANDLER_TEST_README.md` | 5.4 KB | Detailed documentation |
| `TEST_SUITE_SUMMARY.md` | This file | Quick reference |

## Quick Start

### Windows (Recommended)
```bash
cd MLS\tests
run_image_handler_test.bat
```

### Python (Cross-platform)
```bash
cd MLS/tests

# Run full test
python test_image_handler_with_mhi_cam.py

# Limit to 50 images
python test_image_handler_with_mhi_cam.py --max-images 50

# Visualize results
python visualize_image_handler_results.py
```

## What It Tests

The test suite validates:

1. **Image Loading** - OpenCV reads JPG files from mhi_cam
2. **Ion Detection** - Peak finding + Gaussian fitting
3. **Overlay Generation** - Circles, crosshairs, parameter text
4. **JSON Export** - Ion positions and fit data
5. **Performance** - Processing time per frame

## Input Images

- **Source**: `mhi_cam/output_images/`
- **Format**: JPG frames from camera
- **Count**: ~500 test images available
- **Content**: Real ion trap images with ions

## Output Structure

```
MLS/tests/output/image_handler_test/
├── labelled_frames/          # Processed images with overlays
│   ├── 2024_08_09_4_frame_0_labelled.jpg
│   └── ...
├── ion_data/                 # JSON files
│   ├── ion_data_2024_08_09_4_frame_0.json
│   └── ...
├── report.txt                # Text summary
├── report.json               # Machine-readable report
└── comparison.html           # Visual comparison page
```

## Key Features

### 1. Batch Processing
Processes all images in mhi_cam/output_images/ with progress display:
```
[1/500] Processing 2024_08_09_4_frame_0.jpg...
✓ 2024_08_09_4_frame_0.jpg: 2 ions detected in 45.2ms
```

### 2. Statistics Collection
- Total images processed
- Success/failure rate
- Ions detected per image
- Average processing time
- Total elapsed time

### 3. Visual Comparison
Interactive viewer shows:
- Original image (left)
- Labelled image (right)
- Auto-advance or manual control
- Pause/resume functionality

### 4. Configurable ROI
```bash
# Test different regions of interest
python test_image_handler_with_mhi_cam.py --roi 200 250 400 500
```

## Success Criteria

| Metric | Target | Notes |
|--------|--------|-------|
| Success Rate | > 90% | Images successfully processed |
| Processing Time | < 100ms | Per frame average |
| Ions Detected | > 0 | For frames containing ions |

## Example Output

### Console Output
```
============================================================
Image Handler Test - Using mhi_cam Images
============================================================
Input path: D:\mhi_cam\output_images
Output path: D:\MLS\tests\output\image_handler_test
ROI: (180, 220, 425, 495)
============================================================
Found 500 test images
[1/500] Processing 2024_08_09_4_frame_0.jpg...
✓ 2024_08_09_4_frame_0.jpg: 2 ions detected in 45.2ms
...
============================================================
Test Complete!
============================================================
Total images: 500
Successful: 498
Failed: 2
Success rate: 99.6%
Total ions detected: 523
Avg processing time: 42.3ms
Total time: 21.1s
```

### JSON Report (report.json)
```json
{
  "test_date": "2026-02-02T14:30:15",
  "total_images": 500,
  "successful": 498,
  "failed": 2,
  "success_rate": 99.6,
  "total_ions_detected": 523,
  "avg_processing_time_ms": 42.3,
  "results": [...]
}
```

## Integration Notes

After successful testing, the `image_handler.py` can be:

1. **Used standalone**:
   ```python
   from server.cam.image_handler import ImageHandler
   handler = ImageHandler()
   handler.start()
   ```

2. **Integrated with camera server**:
   - Automatic processing of new frames
   - Real-time ion detection
   - JSON export to E:/Data/ion_data/

3. **Used in analysis pipeline**:
   - Post-processing of captured frames
   - Batch analysis of experiments

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No test images found" | Check mhi_cam at `../../mhi_cam/output_images` |
| Import errors | Install requirements: `pip install opencv-python numpy scipy` |
| No ions detected | Adjust ROI: `--roi 0 1024 0 1024` for full frame |
| Slow processing | Reduce ROI size or use `--max-images` for testing |

## Next Steps

1. **Run the test**: `run_image_handler_test.bat`
2. **Check the report**: Open `output/image_handler_test/report.txt`
3. **Visualize results**: `python visualize_image_handler_results.py`
4. **Review labelled frames**: Check `output/image_handler_test/labelled_frames/`
5. **Deploy**: Copy working configuration to production

---

**Test Suite Created**: 2026-02-02
**Compatible with**: MLS image_handler v1.0
