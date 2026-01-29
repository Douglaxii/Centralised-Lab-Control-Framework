"""
Mock DCAM-API module for testing without Hamamatsu camera hardware.
This is a stub implementation that simulates camera operations.

For actual camera operation, install the Hamamatsu DCAM-API SDK:
1. Install DCAM-API SDK from Hamamatsu website
2. Copy dcamcon.py, dcamapi4.py, dcimgnp.py from SDK to this directory
3. Replace this mock with the actual implementation
"""

import time
import random
import numpy as np
from datetime import datetime


class MockDcam:
    """Mock DCAM camera object."""
    
    def __init__(self):
        self.__hdcam = 1  # Fake handle
        self.width = 1024
        self.height = 1024
        self.properties = {
            'SENSORCOOLERSTATUS': 2,  # ON
            'SENSORTEMPERATURE': -20.0,
            'EXPOSURETIME': 0.3,
            'TRIGGERSOURCE': 2,  # EXTERNAL
            'TRIGGER_MODE': 1,  # NORMAL
            'IMAGE_PIXELTYPE': 0x00000002,  # MONO16
        }
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
    
    def dev_open(self, index):
        return True
    
    def dev_close(self):
        pass
    
    def dev_getstring(self, idstr):
        return "Mock Hamamatsu Camera"
    
    def prop_getvalue(self, idprop):
        return self.properties.get(idprop, 0)
    
    def prop_setvalue(self, idprop, value):
        self.properties[idprop] = value
        return True
    
    def buf_alloc(self, n_frames):
        return True
    
    def buf_release(self):
        return True
    
    def cap_start(self, mode):
        return True
    
    def cap_stop(self):
        return True
    
    def cap_firetrigger(self):
        return True
    
    def wait_capevent_frameready(self, timeout):
        time.sleep(0.1)  # Simulate frame acquisition
        return True
    
    def buf_getlastframedata(self):
        # Generate a synthetic frame with Gaussian spots
        frame = np.zeros((self.height, self.width), dtype=np.uint16)
        
        # Add some "ions" (Gaussian spots)
        num_ions = random.randint(1, 5)
        for _ in range(num_ions):
            cx = random.randint(200, 800)
            cy = random.randint(200, 800)
            amp = random.randint(1000, 5000)
            
            y, x = np.ogrid[:self.height, :self.width]
            spot = amp * np.exp(-((x-cx)**2 + (y-cy)**2) / (2 * 15**2))
            frame += spot.astype(np.uint16)
        
        # Add noise
        frame += np.random.normal(100, 20, frame.shape).astype(np.uint16)
        
        return frame


class Dcamcon:
    """Mock DCAM connection class."""
    
    def __init__(self):
        self.dcam = MockDcam()
        self.is_open = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
    
    def open(self, index=0):
        self.is_open = True
        return True
    
    def close(self):
        self.is_open = False
    
    def is_opened(self):
        return self.is_open
    
    def get_propertyvalue(self, property_id, default=False):
        return self.dcam.properties.get(property_id, default)
    
    def set_propertyvalue(self, property_id, value):
        self.dcam.properties[property_id] = value
        return True
    
    def firetrigger(self):
        return True
    
    def wait_capevent_frameready(self, timeout):
        return self.dcam.wait_capevent_frameready(timeout)
    
    def buf_getlastframedata(self):
        return self.dcam.buf_getlastframedata()


# Mock DCAM constants
class DCAM_IDPROP:
    SENSORCOOLERSTATUS = 'SENSORCOOLERSTATUS'
    SENSORCOOLER = 'SENSORCOOLER'
    SENSORTEMPERATURE = 'SENSORTEMPERATURE'
    EXPOSURETIME = 'EXPOSURETIME'
    TRIGGERSOURCE = 'TRIGGERSOURCE'
    TRIGGER_MODE = 'TRIGGER_MODE'
    TRIGGERACTIVE = 'TRIGGERACTIVE'
    TRIGGERPOLARITY = 'TRIGGERPOLARITY'
    TRIGGERTIMES = 'TRIGGERTIMES'
    SENSORMODE = 'SENSORMODE'
    READOUTSPEED = 'READOUTSPEED'
    IMAGE_PIXELTYPE = 'IMAGE_PIXELTYPE'
    INTERNAL_FRAMEINTERVAL = 'INTERNAL_FRAMEINTERVAL'
    SUBARRAYHSIZE = 'SUBARRAYHSIZE'
    SUBARRAYHPOS = 'SUBARRAYHPOS'
    SUBARRAYVSIZE = 'SUBARRAYVSIZE'
    SUBARRAYVPOS = 'SUBARRAYVPOS'


class DCAMPROP:
    class SENSORCOOLERSTATUS:
        OFF = 1
        ON = 2
    
    class SENSORCOOLER:
        OFF = 1
        ON = 2
    
    class TRIGGERSOURCE:
        INTERNAL = 1
        EXTERNAL = 2
        SOFTWARE = 3
    
    class TRIGGER_MODE:
        NORMAL = 1
        PIV = 2
        START = 3
    
    class TRIGGERACTIVE:
        EDGE = 1
        LEVEL = 2
    
    class TRIGGERPOLARITY:
        NEGATIVE = 1
        POSITIVE = 2
    
    class SENSORMODE:
        AREA = 1
        LINE = 2
    
    class READOUTSPEED:
        FASTEST = 1


class DCAM_PIXELTYPE:
    MONO8 = 0x00000001
    MONO16 = 0x00000002


class DCAMERR:
    TIMEOUT = 0x80000200


# Mock API functions
def dcamapi_init():
    """Initialize DCAM-API."""
    print("[MOCK] DCAM-API initialized")
    return True


def dcamapi_uninit():
    """Uninitialize DCAM-API."""
    print("[MOCK] DCAM-API uninitialized")
    return True


def dcamapi_getdevicecount():
    """Get number of connected cameras."""
    return 1  # One mock camera


# Convenience functions for camera_recording.py
def dcamcon_init():
    """Initialize DCAM connection."""
    print("[MOCK] DCAM connection initialized")
    return True


def dcamcon_uninit():
    """Uninitialize DCAM connection."""
    print("[MOCK] DCAM connection uninitialized")
    return True


def dcamcon_choose_and_open():
    """Choose and open a camera."""
    dcamcon = Dcamcon()
    dcamcon.open()
    print("[MOCK] Camera opened")
    return dcamcon


def dcambuf_alloc(hdcam, n_frames):
    """Allocate buffer."""
    return 1  # Success


def dcambuf_lockframe(hdcam, frame):
    """Lock frame buffer."""
    return 1  # Success


def dcambuf_copyframe(hdcam, frame):
    """Copy frame data."""
    return 1  # Success


def dcamcap_start(hdcam, mode):
    """Start capture."""
    return True


def dcamcap_stop(hdcam):
    """Stop capture."""
    return True


def dcamcap_record(hdcam, hrec):
    """Start recording."""
    return 1  # Success


def dcamrec_open(recopen):
    """Open record file."""
    return 1  # Success


def dcamrec_close(hrec):
    """Close record file."""
    return True


# Mock classes
def DCAMBUF_FRAME():
    """Mock frame buffer structure."""
    class Frame:
        def __init__(self):
            self.size = 0
            self.iFrame = 0
            self.buf = None
            self.width = 1024
            self.height = 1024
    return Frame()


def DCAMREC_OPEN():
    """Mock record open structure."""
    class RecOpen:
        def __init__(self):
            self.size = 0
            self.hrec = 1
            self.setpath = lambda x: None
            self.ext = 'dcimg'
            self.maxframepersession = 100
    return RecOpen()


# Sizeof mock
def sizeof(obj):
    return 0


# Print warning when module loads
print("[WARNING] Using MOCK dcamcon module - no actual camera connected!")
print("[WARNING] For real camera operation, install Hamamatsu DCAM-API SDK")
