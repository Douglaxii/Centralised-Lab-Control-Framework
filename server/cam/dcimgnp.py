"""
Mock DCIMG file handling module.
This is a stub for testing without Hamamatsu SDK.
"""

import numpy as np


class DcimgFile:
    """Mock DCIMG file handler."""
    
    def __init__(self, path=None):
        self.path = path
        self.frame_count = 0
        self.width = 1024
        self.height = 1024
    
    def open(self, path):
        self.path = path
        print(f"[MOCK] Opened DCIMG file: {path}")
        return True
    
    def close(self):
        print(f"[MOCK] Closed DCIMG file: {self.path}")
    
    def get_frame_count(self):
        return self.frame_count
    
    def get_frame(self, index):
        """Return a mock frame."""
        return np.random.randint(0, 65535, (self.height, self.width), dtype=np.uint16)


def dcimg_open(path):
    """Open a DCIMG file."""
    return DcimgFile(path)
