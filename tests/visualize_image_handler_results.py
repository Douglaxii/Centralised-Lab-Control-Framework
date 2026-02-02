"""
Visualize Image Handler Results

Displays original images side-by-side with labelled versions.
Useful for quick visual verification of ion detection.

Usage:
    python visualize_image_handler_results.py
    python visualize_image_handler_results.py --test-output output/image_handler_test
"""

import os
import sys
import argparse
from pathlib import Path

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("ERROR: OpenCV required. Run: pip install opencv-python")
    sys.exit(1)


def create_side_by_side_comparison(original_path: Path, labelled_path: Path) -> np.ndarray:
    """Create side-by-side comparison image."""
    orig = cv2.imread(str(original_path))
    labelled = cv2.imread(str(labelled_path))
    
    if orig is None or labelled is None:
        return None
    
    # Resize to same height if needed
    h_orig, w_orig = orig.shape[:2]
    h_label, w_label = labelled.shape[:2]
    
    if h_orig != h_label:
        scale = h_orig / h_label
        new_w = int(w_label * scale)
        labelled = cv2.resize(labelled, (new_w, h_orig))
    
    # Combine side by side
    combined = np.hstack([orig, labelled])
    
    # Add labels
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(combined, "Original", (10, 30), font, 1, (0, 255, 0), 2)
    cv2.putText(combined, "Labelled", (w_orig + 10, 30), font, 1, (0, 255, 0), 2)
    
    return combined


def main():
    parser = argparse.ArgumentParser(description="Visualize image handler results")
    parser.add_argument(
        "--test-output",
        type=str,
        default="output/image_handler_test",
        help="Path to test output directory"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=500,
        help="Delay between images in ms (default: 500)"
    )
    args = parser.parse_args()
    
    output_path = Path(args.test_output)
    labelled_frames_path = output_path / "labelled_frames"
    ion_data_path = output_path / "ion_data"
    
    if not labelled_frames_path.exists():
        print(f"ERROR: Labelled frames not found at {labelled_frames_path}")
        print("Please run test_image_handler_with_mhi_cam.py first")
        return 1
    
    # Find all labelled frames
    labelled_files = sorted(labelled_frames_path.glob("*_labelled.jpg"))
    
    if not labelled_files:
        print(f"ERROR: No labelled frames found in {labelled_frames_path}")
        return 1
    
    print(f"Found {len(labelled_files)} labelled frames")
    print("Press 'q' to quit, 'p' to pause, any other key for next image")
    print()
    
    # Get corresponding mhi_cam images
    mhi_cam_path = Path("../../mhi_cam/output_images")
    
    current_idx = 0
    paused = False
    
    while True:
        labelled_file = labelled_files[current_idx]
        
        # Find original file
        original_name = labelled_file.name.replace("_labelled", "")
        original_file = mhi_cam_path / original_name
        
        if not original_file.exists():
            # Try without replacing (some files might already have _labelled in name)
            original_name = labelled_file.stem.replace("_labelled", "") + ".jpg"
            original_file = mhi_cam_path / original_name
        
        # Create comparison
        if original_file.exists():
            comparison = create_side_by_side_comparison(original_file, labelled_file)
        else:
            # Just show labelled if original not found
            comparison = cv2.imread(str(labelled_file))
            cv2.putText(comparison, f"Original not found: {original_name}", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        if comparison is None:
            print(f"Failed to load: {labelled_file}")
            current_idx = (current_idx + 1) % len(labelled_files)
            continue
        
        # Resize for display if too large
        max_width = 1600
        max_height = 900
        h, w = comparison.shape[:2]
        
        if w > max_width or h > max_height:
            scale = min(max_width / w, max_height / h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            comparison = cv2.resize(comparison, (new_w, new_h))
        
        # Add info text
        info_text = f"Image {current_idx + 1}/{len(labelled_files)}: {labelled_file.name}"
        cv2.putText(comparison, info_text, (10, comparison.shape[0] - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Show
        cv2.imshow("Image Handler Results (Press 'q' to quit, 'p' to pause)", comparison)
        
        if not paused:
            key = cv2.waitKey(args.delay) & 0xFF
        else:
            key = cv2.waitKey(0) & 0xFF
        
        if key == ord('q'):
            break
        elif key == ord('p'):
            paused = not paused
            print("Paused" if paused else "Resumed")
        elif key == ord('n') or not paused:
            current_idx = (current_idx + 1) % len(labelled_files)
        elif key == ord('b'):
            current_idx = (current_idx - 1) % len(labelled_files)
    
    cv2.destroyAllWindows()
    print("Visualization complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
