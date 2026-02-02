"""
Ion Detection Parameter Tuning Tool

Interactive tool to find optimal detection parameters for mhi_cam images.

Usage:
    python tune_ion_detection.py
    
Controls:
    +/- : Adjust threshold percentile
    [/] : Adjust min_distance
    {/} : Adjust min_sigma
    :/" : Adjust max_sigma
    u/j : Adjust ROI y_start
    i/k : Adjust ROI y_finish
    y/h : Adjust ROI x_start
    o/l : Adjust ROI x_finish
    r   : Reset to defaults
    s   : Save current parameters
    q   : Quit
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any

import cv2
import numpy as np

# Add paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "server" / "cam"))

from image_handler_optimized import OptimizedImageHandler


class TuningTool:
    """Interactive tuning tool for ion detection."""
    
    def __init__(self, image_path: Path):
        self.image_path = image_path
        self.frame = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        
        if self.frame is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        # Default parameters
        self.params = {
            "roi": [200, 400, 300, 500],  # x_start, x_finish, y_start, y_finish
            "threshold_percentile": 99.5,
            "min_snr": 5.0,
            "min_distance": 15,
            "min_sigma": 2.0,
            "max_sigma": 30.0,
            "scales": [3, 5, 7]
        }
        
        self.param_step = {
            "threshold_percentile": 0.1,
            "min_snr": 0.5,
            "min_distance": 1,
            "min_sigma": 0.5,
            "max_sigma": 1.0
        }
        
        self.current_result = None
        
    def create_handler(self) -> OptimizedImageHandler:
        """Create handler with current parameters."""
        handler = OptimizedImageHandler(
            raw_frames_path=Path("dummy"),
            labelled_frames_path=Path("dummy"),
            ion_data_path=Path("dummy"),
            roi=tuple(self.params["roi"])
        )
        
        # Override other parameters
        handler.threshold_percentile = self.params["threshold_percentile"]
        handler.min_snr = self.params["min_snr"]
        handler.min_distance = self.params["min_distance"]
        handler.min_sigma = self.params["min_sigma"]
        handler.max_sigma = self.params["max_sigma"]
        handler.scales = self.params["scales"]
        
        return handler
    
    def process(self) -> np.ndarray:
        """Process image and return overlay."""
        handler = self.create_handler()
        ions = handler._detect_ions(self.frame)
        overlay = handler._create_overlay(self.frame, ions)
        
        self.current_result = {
            "num_ions": len(ions),
            "ions": ions
        }
        
        return overlay
    
    def add_info_panel(self, image: np.ndarray) -> np.ndarray:
        """Add parameter info panel to image."""
        h, w = image.shape[:2]
        
        # Create side panel
        panel_width = 350
        panel = np.zeros((h, panel_width, 3), dtype=np.uint8)
        
        # Add text
        y = 30
        dy = 25
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        color = (0, 255, 0)
        
        lines = [
            "=== ION DETECTION TUNING ===",
            "",
            f"Image: {self.image_path.name[:25]}",
            f"Frame size: {self.frame.shape[1]}x{self.frame.shape[0]}",
            "",
            "=== PARAMETERS ===",
            f"ROI: {self.params['roi']}",
            f"  Y: u/j={self.params['roi'][2]}, i/k={self.params['roi'][3]}",
            f"  X: y/h={self.params['roi'][0]}, o/l={self.params['roi'][1]}",
            "",
            f"Threshold: {self.params['threshold_percentile']:.1f}% (+/-)",
            f"Min SNR: {self.params['min_snr']:.1f} (n/m)",
            f"Min dist: {self.params['min_distance']} ([/])",
            f"Min sigma: {self.params['min_sigma']:.1f} ({{/}})",
            f"Max sigma: {self.params['max_sigma']:.1f} (:/\")",
            "",
            "=== RESULTS ===",
            f"Ions detected: {self.current_result['num_ions'] if self.current_result else 0}",
            "",
            "=== CONTROLS ===",
            "r = Reset parameters",
            "s = Save parameters",
            "q = Quit",
        ]
        
        for line in lines:
            cv2.putText(panel, line, (10, y), font, font_scale, color, 1)
            y += dy
        
        # Combine image and panel
        combined = np.hstack([image, panel])
        return combined
    
    def adjust_param(self, param: str, delta: float):
        """Adjust parameter value."""
        if param == "roi_x_start":
            self.params["roi"][0] = max(0, min(self.frame.shape[1] - 10, 
                                               self.params["roi"][0] + int(delta * 10)))
        elif param == "roi_x_finish":
            self.params["roi"][1] = max(self.params["roi"][0] + 10, 
                                        min(self.frame.shape[1], 
                                            self.params["roi"][1] + int(delta * 10)))
        elif param == "roi_y_start":
            self.params["roi"][2] = max(0, min(self.frame.shape[0] - 10, 
                                               self.params["roi"][2] + int(delta * 10)))
        elif param == "roi_y_finish":
            self.params["roi"][3] = max(self.params["roi"][2] + 10, 
                                        min(self.frame.shape[0], 
                                            self.params["roi"][3] + int(delta * 10)))
        else:
            self.params[param] = max(0.1, self.params[param] + delta)
    
    def reset_params(self):
        """Reset to default parameters."""
        self.params = {
            "roi": [200, 400, 300, 500],
            "threshold_percentile": 99.5,
            "min_snr": 5.0,
            "min_distance": 15,
            "min_sigma": 2.0,
            "max_sigma": 30.0,
            "scales": [3, 5, 7]
        }
    
    def save_params(self):
        """Save parameters to file."""
        filename = "ion_detection_params.json"
        with open(filename, 'w') as f:
            json.dump(self.params, f, indent=2)
        print(f"\nParameters saved to: {filename}")
        
    def run(self):
        """Run interactive tuning."""
        print("=" * 60)
        print("Ion Detection Parameter Tuning")
        print("=" * 60)
        print(f"Image: {self.image_path}")
        print("\nControls:")
        print("  +/- : Threshold percentile")
        print("  n/m : Min SNR")
        print("  [/] : Min distance")
        print("  {/} : Min sigma")
        print('  :/" : Max sigma')
        print("  u/j : ROI y_start")
        print("  i/k : ROI y_finish")
        print("  y/h : ROI x_start")
        print("  o/l : ROI x_finish")
        print("  r   : Reset parameters")
        print("  s   : Save parameters")
        print("  q   : Quit")
        print()
        
        window_name = "Ion Detection Tuning (Press 'h' for help)"
        
        while True:
            # Process image
            overlay = self.process()
            display = self.add_info_panel(overlay)
            
            # Resize for display if needed
            max_height = 900
            if display.shape[0] > max_height:
                scale = max_height / display.shape[0]
                display = cv2.resize(display, (int(display.shape[1] * scale), max_height))
            
            cv2.imshow(window_name, display)
            
            key = cv2.waitKey(100) & 0xFF
            
            if key == ord('q'):
                break
            elif key == ord('r'):
                self.reset_params()
                print("Parameters reset to defaults")
            elif key == ord('s'):
                self.save_params()
            elif key == ord('+'):
                self.adjust_param("threshold_percentile", 0.1)
            elif key == ord('-'):
                self.adjust_param("threshold_percentile", -0.1)
            elif key == ord('n'):
                self.adjust_param("min_snr", -0.5)
            elif key == ord('m'):
                self.adjust_param("min_snr", 0.5)
            elif key == ord('['):
                self.adjust_param("min_distance", -1)
            elif key == ord(']'):
                self.adjust_param("min_distance", 1)
            elif key == ord('{'):
                self.adjust_param("min_sigma", -0.5)
            elif key == ord('}'):
                self.adjust_param("min_sigma", 0.5)
            elif key == ord(':'):
                self.adjust_param("max_sigma", -1.0)
            elif key == ord('"'):
                self.adjust_param("max_sigma", 1.0)
            elif key == ord('u'):
                self.adjust_param("roi_y_start", -1)
            elif key == ord('j'):
                self.adjust_param("roi_y_start", 1)
            elif key == ord('i'):
                self.adjust_param("roi_y_finish", -1)
            elif key == ord('k'):
                self.adjust_param("roi_y_finish", 1)
            elif key == ord('y'):
                self.adjust_param("roi_x_start", -1)
            elif key == ord('h'):
                self.adjust_param("roi_x_start", 1)
            elif key == ord('o'):
                self.adjust_param("roi_x_finish", -1)
            elif key == ord('l'):
                self.adjust_param("roi_x_finish", 1)
        
        cv2.destroyAllWindows()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Tune ion detection parameters")
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Path to test image"
    )
    parser.add_argument(
        "--mhi-cam-path",
        type=str,
        default="../mhi_cam/output_images",
        help="Path to mhi_cam images (if --image not specified)"
    )
    
    args = parser.parse_args()
    
    # Determine image path
    if args.image:
        image_path = Path(args.image)
    else:
        mhi_cam_path = Path(args.mhi_cam_path)
        if not mhi_cam_path.exists():
            mhi_cam_path = Path(__file__).parent.parent / ".." / "mhi_cam" / "output_images"
        
        # Find first image
        images = sorted(mhi_cam_path.glob("*.jpg"))
        if not images:
            print(f"No images found in {mhi_cam_path}")
            return 1
        image_path = images[0]
    
    if not image_path.exists():
        print(f"Image not found: {image_path}")
        return 1
    
    # Run tuning tool
    tool = TuningTool(image_path)
    tool.run()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
