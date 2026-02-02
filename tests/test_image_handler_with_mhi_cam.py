"""
Image Handler Test Program - Using mhi_cam Images

This program tests the MLS image_handler module using real camera images
from the mhi_cam repository. It processes JPG frames and outputs:
1. Labelled frames with ion detection overlays
2. JSON files with ion position and fit data

Usage:
    # Run full test suite
    python tests/test_image_handler_with_mhi_cam.py
    
    # Run with specific image subset
    python tests/test_image_handler_with_mhi_cam.py --max-images 10
    
    # Run with custom ROI
    python tests/test_image_handler_with_mhi_cam.py --roi 200 250 400 500

Output Structure:
    MLS/tests/output/image_handler_test/
    ├── labelled_frames/       # Processed frames with overlays
    │   └── frame_*.jpg
    ├── ion_data/              # JSON files with ion positions
    │   └── ion_data_*.json
    ├── report.txt             # Test summary report
    └── comparison.html        # Visual comparison page
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import shutil

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import required modules
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("ERROR: OpenCV not installed. Run: pip install opencv-python")
    sys.exit(1)

try:
    from scipy import ndimage
    from scipy.optimize import curve_fit
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("WARNING: SciPy not installed. Some features disabled.")

# Import MLS image_handler
sys.path.insert(0, str(project_root / "server" / "cam"))
from image_handler import ImageHandler, IonFitResult, FrameData


@dataclass
class TestResult:
    """Result from testing a single image."""
    image_name: str
    success: bool
    ions_detected: int
    processing_time_ms: float
    error_message: Optional[str] = None
    ion_data: Optional[Dict] = None


class ImageHandlerTester:
    """
    Test harness for image_handler using mhi_cam images.
    """
    
    def __init__(self, 
                 mhi_cam_images_path: Path,
                 output_path: Path,
                 roi: Tuple[int, int, int, int] = (0, 500, 10, 300),
                 max_images: Optional[int] = None):
        """
        Initialize tester.
        
        Args:
            mhi_cam_images_path: Path to mhi_cam images (e.g., output_images)
            output_path: Path for test outputs
            roi: Region of interest (x_start, x_finish, y_start, y_finish)
            max_images: Maximum number of images to test (None for all)
        """
        self.mhi_cam_images_path = mhi_cam_images_path
        self.output_path = output_path
        self.roi = roi
        self.max_images = max_images
        
        # Setup logging
        self.logger = self._setup_logging()
        
        # Create output directories
        self.labelled_frames_path = output_path / "labelled_frames"
        self.ion_data_path = output_path / "ion_data"
        self.ion_uncertainty_path = output_path / "ion_uncertainty"
        self._create_directories()
        
        # Statistics
        self.results: List[TestResult] = []
        self.start_time = None
        self.end_time = None
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration."""
        logger = logging.getLogger("ImageHandlerTest")
        logger.setLevel(logging.INFO)
        
        # Console handler
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
        )
        console.setFormatter(formatter)
        logger.addHandler(console)
        
        return logger
    
    def _create_directories(self):
        """Create output directories."""
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.labelled_frames_path.mkdir(exist_ok=True)
        self.ion_data_path.mkdir(exist_ok=True)
        self.ion_uncertainty_path.mkdir(exist_ok=True)
        
    def find_test_images(self) -> List[Path]:
        """
        Find all JPG images in mhi_cam directory.
        
        Returns:
            List of image file paths
        """
        if not self.mhi_cam_images_path.exists():
            self.logger.error(f"Path not found: {self.mhi_cam_images_path}")
            return []
        
        # Find all JPG files
        image_files = list(self.mhi_cam_images_path.glob("*.jpg"))
        
        # Sort by name for consistent ordering
        image_files.sort()
        
        # Limit if specified
        if self.max_images and len(image_files) > self.max_images:
            self.logger.info(f"Limiting to {self.max_images} images (found {len(image_files)})")
            image_files = image_files[:self.max_images]
        
        self.logger.info(f"Found {len(image_files)} test images")
        return image_files
    
    def process_single_image(self, image_path: Path) -> TestResult:
        """
        Process a single image using image_handler functionality.
        
        Args:
            image_path: Path to image file
            
        Returns:
            TestResult with processing information
        """
        start_time = time.time()
        image_name = image_path.name
        
        try:
            # Read image
            frame = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
            if frame is None:
                return TestResult(
                    image_name=image_name,
                    success=False,
                    ions_detected=0,
                    processing_time_ms=0,
                    error_message="Could not read image"
                )
            
            # Create image handler instance for processing
            handler = ImageHandler(
                raw_frames_path=self.output_path / "dummy_raw",
                labelled_frames_path=self.labelled_frames_path,
                ion_data_path=self.ion_data_path,
                ion_uncertainty_path=self.ion_uncertainty_path,
                roi=self.roi
            )
            
            # Detect ions
            ions = handler._detect_ions(frame)
            
            # Create overlay
            overlay_frame = handler._create_overlay(frame, ions)
            
            # Save labelled frame
            labelled_filename = f"{image_path.stem}_labelled.jpg"
            cv2.imwrite(str(self.labelled_frames_path / labelled_filename), overlay_frame)
            
            # Create frame data
            frame_data = FrameData(
                timestamp=datetime.now().isoformat(),
                frame_number=0,
                ions={f"ion_{i+1}": ion.to_dict() for i, ion in enumerate(ions)},
                fit_quality=sum(ion.fit_quality for ion in ions) / len(ions) if ions else 0.0,
                processing_time_ms=(time.time() - start_time) * 1000
            )
            
            # Save ion data
            ion_filename = f"ion_data_{image_path.stem}.json"
            with open(self.ion_data_path / ion_filename, 'w') as f:
                json.dump(frame_data.to_dict(), f, indent=2)
            
            # Save ion uncertainty data separately
            if ions:
                uncertainty_data = {
                    "timestamp": datetime.now().isoformat(),
                    "frame_number": 0,
                    "image_name": image_name,
                    "ions": {f"ion_{i+1}": ion.to_uncertainty_dict() for i, ion in enumerate(ions)}
                }
                uncertainty_filename = f"ion_uncertainty_{image_path.stem}.json"
                with open(self.ion_uncertainty_path / uncertainty_filename, 'w') as f:
                    json.dump(uncertainty_data, f, indent=2)
            
            processing_time = (time.time() - start_time) * 1000
            
            self.logger.info(
                f"[OK] {image_name}: {len(ions)} ions detected in {processing_time:.1f}ms"
            )
            
            return TestResult(
                image_name=image_name,
                success=True,
                ions_detected=len(ions),
                processing_time_ms=processing_time,
                ion_data=frame_data.to_dict()
            )
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            self.logger.error(f"✗ {image_name}: {e}")
            return TestResult(
                image_name=image_name,
                success=False,
                ions_detected=0,
                processing_time_ms=processing_time,
                error_message=str(e)
            )
    
    def run_tests(self) -> Dict[str, Any]:
        """
        Run tests on all found images.
        
        Returns:
            Dictionary with test statistics
        """
        self.logger.info("=" * 60)
        self.logger.info("Image Handler Test - Using mhi_cam Images")
        self.logger.info("=" * 60)
        self.logger.info(f"Input path: {self.mhi_cam_images_path}")
        self.logger.info(f"Output path: {self.output_path}")
        self.logger.info(f"ROI: {self.roi}")
        self.logger.info("=" * 60)
        
        # Find images
        image_files = self.find_test_images()
        if not image_files:
            self.logger.error("No test images found!")
            return {"success": False, "error": "No images found"}
        
        # Process each image
        self.start_time = time.time()
        
        for i, image_path in enumerate(image_files, 1):
            self.logger.info(f"[{i}/{len(image_files)}] Processing {image_path.name}...")
            result = self.process_single_image(image_path)
            self.results.append(result)
        
        self.end_time = time.time()
        
        # Generate report
        return self._generate_report()
    
    def _generate_report(self) -> Dict[str, Any]:
        """
        Generate test report.
        
        Returns:
            Dictionary with test statistics
        """
        total_images = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        failed = total_images - successful
        total_ions = sum(r.ions_detected for r in self.results)
        avg_time = sum(r.processing_time_ms for r in self.results) / total_images if total_images > 0 else 0
        
        total_time = self.end_time - self.start_time if self.end_time and self.start_time else 0
        
        report = {
            "test_date": datetime.now().isoformat(),
            "total_images": total_images,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total_images * 100) if total_images > 0 else 0,
            "total_ions_detected": total_ions,
            "avg_processing_time_ms": avg_time,
            "total_time_seconds": total_time,
            "roi": self.roi,
            "output_path": str(self.output_path),
            "results": [
                {
                    "image_name": r.image_name,
                    "success": r.success,
                    "ions_detected": r.ions_detected,
                    "processing_time_ms": r.processing_time_ms,
                    "error": r.error_message
                }
                for r in self.results
            ]
        }
        
        # Save JSON report
        report_file = self.output_path / "report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Save text report
        text_report = self._format_text_report(report)
        text_report_file = self.output_path / "report.txt"
        with open(text_report_file, 'w', encoding='utf-8') as f:
            f.write(text_report)
        
        # Print summary
        self.logger.info("=" * 60)
        self.logger.info("Test Complete!")
        self.logger.info("=" * 60)
        self.logger.info(f"Total images: {total_images}")
        self.logger.info(f"Successful: {successful}")
        self.logger.info(f"Failed: {failed}")
        self.logger.info(f"Success rate: {report['success_rate']:.1f}%")
        self.logger.info(f"Total ions detected: {total_ions}")
        self.logger.info(f"Avg processing time: {avg_time:.1f}ms")
        self.logger.info(f"Total time: {total_time:.1f}s")
        self.logger.info(f"Report saved: {report_file}")
        self.logger.info(f"Labelled frames: {self.labelled_frames_path}")
        self.logger.info(f"Ion data: {self.ion_data_path}")
        self.logger.info(f"Ion uncertainty: {self.ion_uncertainty_path}")
        
        return report
    
    def _format_text_report(self, report: Dict) -> str:
        """Format report as text."""
        lines = [
            "=" * 60,
            "Image Handler Test Report",
            "=" * 60,
            f"Test Date: {report['test_date']}",
            f"ROI: {report['roi']}",
            "",
            "Summary Statistics:",
            f"  Total images: {report['total_images']}",
            f"  Successful: {report['successful']}",
            f"  Failed: {report['failed']}",
            f"  Success rate: {report['success_rate']:.1f}%",
            f"  Total ions detected: {report['total_ions_detected']}",
            f"  Avg processing time: {report['avg_processing_time_ms']:.1f}ms",
            f"  Total time: {report['total_time_seconds']:.1f}s",
            "",
            "Individual Results:",
            "-" * 60,
        ]
        
        for r in report['results']:
            status = "[OK]" if r['success'] else "[FAIL]"
            lines.append(f"{status} {r['image_name']}")
            lines.append(f"    Ions: {r['ions_detected']}, Time: {r['processing_time_ms']:.1f}ms")
            if r['error']:
                lines.append(f"    Error: {r['error']}")
        
        lines.extend([
            "-" * 60,
            "Output Locations:",
            f"  Labelled frames: {self.labelled_frames_path}",
            f"  Ion data: {self.ion_data_path}",
            f"  Ion uncertainty: {self.ion_uncertainty_path}",
            "=" * 60,
        ])
        
        return "\n".join(lines)
    
    def create_comparison_html(self):
        """Create HTML page comparing original and labelled images."""
        html_file = self.output_path / "comparison.html"
        
        test_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_images = len(self.results)
        success_rate = sum(1 for r in self.results if r.success) / len(self.results) * 100 if self.results else 0
        
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Image Handler Test Results</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        .summary {{ background: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .image-pair {{ 
            display: flex; 
            gap: 20px; 
            margin-bottom: 30px; 
            background: white; 
            padding: 15px; 
            border-radius: 5px;
        }}
        .image-container {{ flex: 1; }}
        .image-container img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
        .image-title {{ font-weight: bold; margin-bottom: 10px; color: #555; }}
        .status-success {{ color: green; }}
        .status-fail {{ color: red; }}
    </style>
</head>
<body>
    <h1>Image Handler Test Results</h1>
    <div class="summary">
        <h2>Summary</h2>
        <p>Test Date: {test_date}</p>
        <p>Total Images: {total_images}</p>
        <p>Success Rate: {success_rate:.1f}%</p>
        <p>ROI: {self.roi}</p>
    </div>
"""
        
        # Add image pairs
        for result in self.results:
            if not result.success:
                continue
                
            original_name = result.image_name
            labelled_name = f"{Path(original_name).stem}_labelled.jpg"
            
            html_content += f"""
    <div class="image-pair">
        <div class="image-container">
            <div class="image-title">Original: {original_name}</div>
            <img src="../mhi_cam_images/{original_name}" alt="Original" onerror="this.src=''"/>
        </div>
        <div class="image-container">
            <div class="image-title">Labelled: {labelled_name}</div>
            <img src="labelled_frames/{labelled_name}" alt="Labelled"/>
            <p>Ions detected: {result.ions_detected}</p>
            <p>Processing time: {result.processing_time_ms:.1f}ms</p>
        </div>
    </div>
"""
        
        html_content += """
</body>
</html>
"""
        
        with open(html_file, 'w') as f:
            f.write(html_content)
        
        self.logger.info(f"Comparison HTML saved: {html_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test MLS image_handler using mhi_cam images"
    )
    parser.add_argument(
        "--mhi-cam-path",
        type=str,
        default="../mhi_cam/output_images",
        help="Path to mhi_cam images (default: ../mhi_cam/output_images)"
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="tests/output/image_handler_test",
        help="Output path for test results"
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=None,
        help="Maximum number of images to test"
    )
    parser.add_argument(
        "--roi",
        type=int,
        nargs=4,
        metavar=('X_START', 'X_FINISH', 'Y_START', 'Y_FINISH'),
        default=[0, 500, 10, 300],
        help="Region of interest (default: 0 500 10 300)"
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    mhi_cam_path = Path(args.mhi_cam_path)
    if not mhi_cam_path.is_absolute():
        mhi_cam_path = project_root / mhi_cam_path
    
    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = project_root / output_path
    
    # Create and run tester
    tester = ImageHandlerTester(
        mhi_cam_images_path=mhi_cam_path,
        output_path=output_path,
        roi=tuple(args.roi),
        max_images=args.max_images
    )
    
    # Run tests
    report = tester.run_tests()
    
    # Create comparison HTML
    tester.create_comparison_html()
    
    # Return exit code based on success
    if report.get('success_rate', 0) > 80:
        print("\n[PASS] Tests PASSED (>80% success rate)")
        return 0
    else:
        print("\n[FAIL] Tests FAILED (<80% success rate)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
