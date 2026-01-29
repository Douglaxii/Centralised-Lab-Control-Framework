"""
Mock live capturing module.
This is a stub for testing without Hamamatsu SDK.
"""

import cv2
import numpy as np


def show_framedata(frame, window_name="Camera"):
    """
    Mock function to display frame data.
    In real implementation, this would show live preview.
    """
    # Just log that we would display the frame
    print(f"[MOCK] Would display frame {frame.shape if hasattr(frame, 'shape') else 'unknown'} in window '{window_name}'")
    return True
