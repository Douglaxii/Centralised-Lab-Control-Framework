"""
Test script for image_handler
Searches for all JPG files under test_img and tests image_handler processing
"""

import os
import sys
import time
import glob
import json
import cv2
import numpy as np
from datetime import datetime

# Add parent directory to path to import image_handler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cam.image_handler import Image_Handler


# Configuration
INPUT_DIR = os.path.dirname(os.path.abspath(__file__))  # test_img directory
OUTPUT_DIR = os.path.join(INPUT_DIR, "annotated_output")


def process_image(jpg_path, output_dir):
    """Process a single image and return timing statistics"""
    filename = os.path.basename(jpg_path)
    stats = {
        "filename": filename,
        "start_time": time.time(),
        "init_time_ms": 0,
        "atom_count": 0,
        "success": False,
        "error": None
    }
    
    try:
        # Time the Image_Handler initialization (includes loading + analysis)
        t0 = time.time()
        
        handler = Image_Handler(
            filename=jpg_path,
            xstart=0, xfinish=300,
            ystart=0, yfinish=300,
            analysis=2,  # Full analysis with fitting
            radius=20
        )
        
        stats["init_time_ms"] = (time.time() - t0) * 1000
        
        # Check if image was loaded successfully
        if handler.operation_array is None:
            stats["error"] = "Failed to load image"
            return stats
        
        stats["atom_count"] = handler.atom_count
        
        # Use annotated frame from Image_Handler if ions detected
        if handler.annotated_frame is not None:
            annotated = handler.annotated_frame.copy()
        elif handler.img_rgb is not None:
            annotated = handler.img_rgb.copy()
        else:
            annotated = cv2.cvtColor(handler.operation_array, cv2.COLOR_GRAY2RGB)
        
        # Add summary text at top-left
        summary_text = f"File: {filename}"
        cv2.putText(annotated, summary_text, (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        cv2.putText(annotated, summary_text, (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        
        # Add ion count and timing info
        info_text = f"Ions: {handler.atom_count} | Time: {stats['init_time_ms']:.1f}ms"
        cv2.putText(annotated, info_text, (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        cv2.putText(annotated, info_text, (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        
        # Save annotated image
        output_path = os.path.join(output_dir, f"annotated_{filename}")
        cv2.imwrite(output_path, cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR))
        
        stats["output_path"] = output_path
        stats["success"] = True
        
    except Exception as e:
        stats["error"] = str(e)
    
    return stats


def print_statistics(all_stats):
    """Print timing statistics summary"""
    
    print("\n" + "=" * 80)
    print("TIMING STATISTICS SUMMARY")
    print("=" * 80)
    
    if not all_stats:
        print("No images were processed.")
        return
    
    # Calculate statistics
    times = [s["init_time_ms"] for s in all_stats]
    success_count = sum(1 for s in all_stats if s["success"])
    ion_counts = [s["atom_count"] for s in all_stats]
    
    print(f"\nProcessing Time:")
    print(f"  Count:    {len(times)}")
    print(f"  Mean:     {np.mean(times):.2f} ms")
    print(f"  Std:      {np.std(times):.2f} ms")
    print(f"  Min:      {np.min(times):.2f} ms")
    print(f"  Max:      {np.max(times):.2f} ms")
    print(f"  Median:   {np.median(times):.2f} ms")
    
    print(f"\nIon Detection:")
    print(f"  Total ions detected: {sum(ion_counts)}")
    print(f"  Avg ions per image:  {np.mean(ion_counts):.2f}")
    print(f"  Images with ions:    {sum(1 for c in ion_counts if c > 0)}/{len(ion_counts)}")
    
    print(f"\nSuccess Rate: {success_count}/{len(all_stats)} ({100*success_count/len(all_stats):.1f}%)")
    
    # Per-file breakdown
    print("\n" + "-" * 80)
    print("PER-FILE BREAKDOWN")
    print("-" * 80)
    print(f"{'Filename':<40} {'Ions':>5} {'Time(ms)':>10} {'Status':>10}")
    print("-" * 80)
    
    for s in all_stats:
        status = "OK" if s["success"] else "FAIL"
        print(f"{s['filename'][:40]:<40} {s['atom_count']:>5} {s['init_time_ms']:>10.1f} {status:>10}")


def main():
    """Main test function"""
    
    print("=" * 80)
    print("IMAGE HANDLER TEST")
    print("=" * 80)
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\nInput directory:  {INPUT_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    
    # Find all JPG files recursively under test_img (excluding output folder)
    jpg_pattern = os.path.join(INPUT_DIR, "**", "*.jpg")
    all_jpg_files = glob.glob(jpg_pattern, recursive=True)
    
    # Filter out files from annotated_output folder and previously annotated files
    jpg_files = sorted([
        f for f in all_jpg_files 
        if "annotated_output" not in f and not os.path.basename(f).startswith("annotated_")
    ])
    
    if not jpg_files:
        print(f"\nERROR: No JPG files found under {INPUT_DIR}")
        return
    
    print(f"\nFound {len(jpg_files)} JPG files")
    
    # Show folder breakdown
    folders = {}
    for f in jpg_files:
        folder = os.path.dirname(f).replace(INPUT_DIR, ".")
        folders[folder] = folders.get(folder, 0) + 1
    print("\nFolder breakdown:")
    for folder, count in sorted(folders.items()):
        print(f"  {folder}: {count} files")
    
    # Process each file
    all_stats = []
    
    print(f"\nProcessing {len(jpg_files)} images...")
    print("-" * 80)
    
    for i, jpg_path in enumerate(jpg_files, 1):
        filename = os.path.basename(jpg_path)
        print(f"[{i}/{len(jpg_files)}] {filename}...", end=" ", flush=True)
        
        stats = process_image(jpg_path, OUTPUT_DIR)
        all_stats.append(stats)
        
        if stats["success"]:
            print(f"OK - {stats['atom_count']} ions, {stats['init_time_ms']:.1f}ms")
        else:
            print(f"FAIL - {stats['error']}")
    
    # Print statistics
    print_statistics(all_stats)
    
    # Save detailed results to JSON
    results_path = os.path.join(OUTPUT_DIR, "processing_stats.json")
    with open(results_path, 'w') as f:
        json.dump(all_stats, f, indent=2, default=str)
    print(f"\nResults saved to: {results_path}")
    
    # Count output files
    output_files = glob.glob(os.path.join(OUTPUT_DIR, "annotated_*.jpg"))
    print(f"Generated {len(output_files)} annotated images")


if __name__ == "__main__":
    main()
