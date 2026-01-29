"""
Mock DCAM-API v4 constants and structures.
This is a stub for testing without Hamamatsu SDK.
"""

# Mock error codes
DCAMERR_TIMEOUT = 0x80000200
DCAMERR_SUCCESS = 1

# Mock property IDs
DCAM_IDPROP_SENSORTEMPERATURE = 0x00000010
DCAM_IDPROP_SENSORCOOLERSTATUS = 0x00000011
DCAM_IDPROP_SENSORCOOLER = 0x00000012
DCAM_IDPROP_EXPOSURETIME = 0x00000020
DCAM_IDPROP_TRIGGERSOURCE = 0x00000030
DCAM_IDPROP_TRIGGER_MODE = 0x00000031
DCAM_IDPROP_TRIGGERACTIVE = 0x00000032
DCAM_IDPROP_TRIGGERPOLARITY = 0x00000033
DCAM_IDPROP_TRIGGERTIMES = 0x00000034
DCAM_IDPROP_SENSORMODE = 0x00000040
DCAM_IDPROP_READOUTSPEED = 0x00000050
DCAM_IDPROP_IMAGE_PIXELTYPE = 0x00000060
DCAM_IDPROP_INTERNAL_FRAMEINTERVAL = 0x00000070
DCAM_IDPROP_SUBARRAYHSIZE = 0x00000080
DCAM_IDPROP_SUBARRAYHPOS = 0x00000081
DCAM_IDPROP_SUBARRAYVSIZE = 0x00000082
DCAM_IDPROP_SUBARRAYVPOS = 0x00000083

# Mock functions
def dcamrec_open(recopen):
    return 1

def dcamrec_close(hrec):
    return True

def dcamcap_record(hdcam, hrec):
    return 1

def dcamcap_start(hdcam, mode):
    return True

def dcamcap_stop(hdcam):
    return True

# Mock structures
class DCAMREC_OPEN:
    def __init__(self):
        self.size = 0
        self.hrec = 1
        self.path = ""
        self.ext = "dcimg"
        self.maxframepersession = 100
    
    def setpath(self, path):
        self.path = path
