"""
Compare Original vs Optimized Image Handler

This script compares the ion detection performance of the original
and optimized image handlers using mhi_cam test images.

Usage:
    python compare_image_handlers.py --max-images 20
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass

import numpy as np

# Add paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "server" / "cam"))

import cv2

# Import both handlers
from image_handler import ImageHandler as OriginalHandler
from image_handler_optimized import OptimizedImageHandler


@dataclass
class ComparisonResult:
    image_name: str
    orig_ions: int
    opt_ions: int
    orig_time: float
    opt_time: float
    orig_quality: float
    opt_quality: float


def process_with_handler(handler, image_path: Path) -> Tuple[int, float, float]:
    """
    Process single image with given handler.
    
    Returns:
        (num_ions, processing_time_ms, avg_quality)
    """
    start = time.time()
    
    frame = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if frame is None:
        return 0, 0, 0
    
    ions = handler._detect_ions(frame)
    
    elapsed = (time.time() - start) * 1000
    avg_quality = np.mean([ion.fit_quality for ion in ions]) if ions else 0
    
    return len(ions), elapsed, avg_quality


def compare_handlers(mhi_cam_path: Path, max_images: int = None) -> Dict:
    """Compare original vs optimized handler."""
    
    print("=" * 70)
    print("Image Handler Comparison: Original vs Optimized")
    print("=" * 70)
    
    # Find test images
    image_files = sorted(mhi_cam_path.glob("*.jpg"))
    if not image_files:
        print(f"No images found in {mhi_cam_path}")
        return {}
    
    if max_images:
        image_files = image_files[:max_images]
    
    print(f"Testing with {len(image_files)} images from {mhi_cam_path}")
    print()
    
    # Initialize handlers
    print("Initializing handlers...")
    orig_handler = OriginalHandler(
        raw_frames_path=Path("dummy"),
        labelled_frames_path=Path("dummy"),
        ion_data_path=Path("dummy")
    )
    
    opt_handler = OptimizedImageHandler(
        raw_frames_path=Path("dummy"),
        labelled_frames_path=Path("dummy"),
        ion_data_path=Path("dummy")
    )
    
    # Collect results
    results: List[ComparisonResult] = []
    
    print("\nProcessing images...")
    print("-" * 70)
    print(f"{'Image':<30} {'Orig':>8} {'Opt':>8} {'Gain':>8} | {'Orig t':>8} {'Opt t':>8}")
    print("-" * 70)
    
    for i, img_path in enumerate(image_files, 1):
        # Process with original
        orig_ions, orig_time, orig_qual = process_with_handler(orig_handler, img_path)
        
        # Process with optimized
        opt_ions, opt_time, opt_qual = process_with_handler(opt_handler, img_path)
        
        result = ComparisonResult(
            image_name=img_path.name[:28],
            orig_ions=orig_ions,
            opt_ions=opt_ions,
            orig_time=orig_time,
            opt_time=opt_time,
            orig_quality=orig_qual,
            opt_quality=opt_qual
        )
        results.append(result)
        
        gain = opt_ions - orig_ions
        gain_str = f"+{gain}" if gain > 0 else str(gain)
        
        print(f"{result.image_name:<30} {orig_ions:>8} {opt_ions:>8} {gain_str:>8} | "
              f"{orig_time:>7.1f}ms {opt_time:>7.1f}ms")
    
    print("-" * 70)
    
    # Calculate statistics
    total_orig = sum(r.orig_ions for r in results)
    total_opt = sum(r.opt_ions for r in results)
    avg_orig_time = sum(r.orig_time for r in results) / len(results)
    avg_opt_time = sum(r.opt_time for r in results) / len(results)
    
    images_with_more_ions = sum(1 for r in results if r.opt_ions > r.orig_ions)
    images_with_same_ions = sum(1 for r in results if r.opt_ions == r.orig_ions)
    images_with_fewer_ions = sum(1 for r in results if r.opt_ions < r.orig_ions)
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total images tested: {len(results)}")
    print()
    print("Ion Detection:")
    print(f"  Original:  {total_orig} ions total")
    print(f"  Optimized: {total_opt} ions total")
    print(f"  Improvement: {total_opt - total_orig:+d} ions ({(total_opt/total_orig - 1)*100:.1f}% if > 0)")
    print()
    print("Per-image comparison:")
    print(f"  More ions detected: {images_with_more_ions} images")
    print(f"  Same ions detected: {images_with_same_ions} images")
    print(f"  Fewer ions detected: {images_with_fewer_ions} images")
    print()
    print("Performance:")
    print(f"  Original avg time:  {avg_orig_time:.1f}ms")
    print(f"  Optimized avg time: {avg_opt_time:.1f}ms")
    speedup = avg_orig_time / avg_opt_time if avg_opt_time > 0 else 0
    print(f"  Speedup: {speedup:.2f}x")
    print()
    
    # Detailed comparison for images where we found more ions
    print("Images with improved detection:")
    print("-" * 70)
    for r in results:
        if r.opt_ions > r.orig_ions:
            print(f"  {r.image_name}: {r.orig_ions} → {r.opt_ions} ions (+{r.opt_ions - r.orig_ions})")
    
    return {
        "total_images": len(results),
        "total_orig_ions": total_orig,
        "total_opt_ions": total_opt,
        "improvement": total_opt - total_orig,
        "avg_orig_time_ms": avg_orig_time,
        "avg_opt_time_ms": avg_opt_time,
        "images_with_more": images_with_more_ions,
        "images_with_same": images_with_same_ions,
        "images_with_fewer": images_with_fewer_ions,
        "detailed_results": [
            {
                "image": r.image_name,
                "orig_ions": r.orig_ions,
                "opt_ions": r.opt_ions,
                "orig_time": r.orig_time,
                "opt_time": r.opt_time
            }
            for r in results
        ]
    }


def visualize_comparison(image_path: Path, orig_handler, opt_handler):
    """Create side-by-side visualization of detection results."""
    frame = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if frame is None:
        return None
    
    # Get detections
    orig_ions = orig_handler._detect_ions(frame)
    opt_ions = opt_handler._detect_ions(frame)
    
    # Create overlays
    orig_overlay = orig_handler._create_overlay(frame, orig_ions)
    opt_overlay = opt_handler._create_overlay(frame, opt_ions)
    
    # Resize to same height
    h = max(orig_overlay.shape[0], opt_overlay.shape[0])
    orig_resized = cv2.resize(orig_overlay, (orig_overlay.shape[1] * h // orig_overlay.shape[0], h))
    opt_resized = cv2.resize(opt_overlay, (opt_overlay.shape[1] * h // opt_overlay.shape[0], h))
    
    # Combine
    combined = np.hstack([orig_resized, opt_resized])
    
    # Add labels
    cv2.putText(combined, f"Original: {len(orig_ions)} ions", (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(combined, f"Optimized: {len(opt_ions)} ions", (orig_resized.shape[1] + 10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    
    return combined


def main():
    parser = argparse.ArgumentParser(description="Compare image handlers")
    parser.add_argument(
        "--mhi-cam-path",
        type=str,
        default="../mhi_cam/output_images",
        help="Path to mhi_cam images"
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=20,
        help="Maximum images to test"
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Show visual comparison"
    )
    args = parser.parse_args()
    
    mhi_cam_path = Path(args.mhi_cam_path)
    if not mhi_cam_path.exists():
        # Try relative to script
        mhi_cam_path = project_root / ".." / "mhi_cam" / "output_images"
    
    if not mhi_cam_path.exists():
        print(f"ERROR: mhi_cam images not found at {mhi_cam_path}")
        return 1
    
    # Run comparison
    results = compare_handlers(mhi_cam_path, args.max_images)
    
    # Visual comparison if requested
    if args.visualize and results:
        print("\n" + "=" * 70)
        print("VISUAL COMPARISON")
        print("=" * 70)
        print("Press 'q' to quit, 'n' for next image, 's' to save")
        print()
        
        orig_handler = OriginalHandler(
            raw_frames_path=Path("dummy"),
            labelled_frames_path=Path("dummy"),
            ion_data_path=Path("dummy")
        )
        opt_handler = OptimizedImageHandler(
            raw_frames_path=Path("dummy"),
            labelled_frames_path=Path("dummy"),
            ion_data_path=Path("dummy")
        )
        
        image_files = sorted(mhi_cam_path.glob("*.jpg"))[:args.max_images]
        idx = 0
        
        while True:
            img_path = image_files[idx]
            vis = visualize_comparison(img_path, orig_handler, opt_handler)
            
            if vis is not None:
                # Resize for display
                scale = 0.5
                vis_resized = cv2.resize(vis, (int(vis.shape[1] * scale), int(vis.shape[0] * scale)))
                
                cv2.imshow("Comparison (Original | Optimized)", vis_resized)
                
                key = cv2.waitKey(0) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('n'):
                    idx = (idx + 1) % len(image_files)
                elif key == ord('p'):
                    idx = (idx - 1) % len(image_files)
                elif key == ord('s'):
                    filename = f"comparison_{img_path.stem}.jpg"
                    cv2.imwrite(filename, vis)
                    print(f"Saved: {filename}")
        
        cv2.destroyAllWindows()
    
    # Save JSON report
    if results:
        report_file = Path("handler_comparison_report.json")
        with open(report_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nDetailed report saved: {report_file}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
