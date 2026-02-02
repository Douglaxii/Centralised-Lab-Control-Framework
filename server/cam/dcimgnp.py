"""Dcimgnp module.
This is the module for accessing DCIMG files via DCIMG-API.
This loads DCIMG-API library and implements Dcimg class.
Dcimg class calls DCIMG-API functions and handle the image data with Numpy.
"""

__date__ = '2021-06-18'
__copyright__ = 'Copyright (C) 2021-2024 Hamamatsu Photonics K.K.'

import platform
# for get OS information

import numpy as np
# pip install numpy
# allocated to receive the image data


from enum import IntEnum
# integer enumration class

from ctypes import c_int32, c_uint32, c_void_p, c_char_p
# C language variable types

from ctypes import Structure, POINTER, sizeof, byref
# function to handle C language variable types


# ==== load shared library ====
# abosorb platform dependency

__platform_system = platform.system()
if __platform_system == 'Windows':
    from ctypes import windll
    __dll = windll.LoadLibrary('dcimgapi.dll')
    dcimg_open = __dll.dcimg_openA
else:
    from ctypes import cdll
    __dll = cdll.LoadLibrary('/usr/local/lib/libdcimgapi.so')
    dcimg_open = __dll.dcimg_open


# ==== declare constants ====


class DCIMG_ERR(IntEnum):
    # initialization error
    NOMEMORY = -2147483133  # 0x80000203, not enough memory
    # calling error
    INVALIDHANDLE = -2147481593  # 0x80000807, invalid dcimg value
    INVALIDPARAM = -2147481592  # 0x80000808, invalid parameter, e.g. parameter is NULL
    INVALIDVALUE = -2147481567  # 0x80000821, invalid parameter value
    INVALIDVIEW = -2147481558  # 0x8000082a, invalid view index
    INVALIDFRAMEINDEX = -2147481549  # 0x80000833, the frame index is invalid
    INVALIDSESSIONINDEX = -2147481548  # 0x80000834, the session index is invalid
    FILENOTOPENED = -2147481547  # 0x80000835, file is not opened at dcimg_open()
    UNKNOWNFILEFORMAT = -2147481546  # 0x80000836, opened file format is not supported
    NOTSUPPORT = -2147479805  # 0x80000f03, the function or property are not supportted under current condition
    FAILEDREADDATA = -2080370684  # 0x84001004
    UNKNOWNSIGN = -2080368639  # 0x84001801
    OLDERFILEVERSION = -2080368638  # 0x84001802
    NEWERFILEVERSION = -2080368637  # 0x84001803
    NOIMAGE = -2080368636  # 0x84001804
    UNKNOWNIMAGEPROC = -2080368635  # 0x84001805
    NOTSUPPORTIMAGEPROC = -2080368634  # 0x84001806
    NODATA = -2080368633  # 0x84001807
    IMAGE_UNKNOWNSIGNATURE = -2080362495  # 0x84003001, sigunature of image header is unknown or corrupted
    IMAGE_NEWRUNTIMEREQUIRED = -2080362494  # 0x84003002, version of image header is newer than version that used DCIMG runtime supports
    IMAGE_ERRORSTATUSEXIST = -2080362493  # 0x84003003, image header stands error status
    IMAGE_HEADERCORRUPTED = -2080358396  # 0x84004004, image header value is strange
    INVALIDCODEPAGE = -1916731391  # 0x8DC10001, DCIMG_OPEN::codepage option was incorrect
    UNKNOWNCOMMAND = -2147481599  # 0x80000801, unknown command id
    UNKNOWNPARAMID = -2147481597  # 0x80000803, unkown parameter id
    # success
    SUCCESS = 1  # 1, no error, general success code
    # internal error
    UNREACH = -2147479807  # 0x80000f01, internal error



class DCIMG_IDPARAML(IntEnum):
    NUMBEROF_TOTALFRAME = 0    # number of total frame in the file
    NUMBEROF_FRAME = 2    # number of frame
    SIZEOF_USERDATABIN_FILE = 5    # byte size of file binary USER META DATA.
    SIZEOF_USERDATATEXT_FILE = 8    # byte size of file text USER META DATA.
    IMAGE_WIDTH = 9    # image width
    IMAGE_HEIGHT = 10    # image height
    IMAGE_ROWBYTES = 11    # image rowbytes
    IMAGE_PIXELTYPE = 12    # image pixeltype
    MAXSIZE_USERDATABIN = 13    # maximum byte size of binary USER META DATA
    MAXSIZE_USERDATATEXT = 16    # maximum byte size of text USER META DATA
    NUMBEROF_VIEW = 20    # number of view
    FILEFORMAT_VERSION = 21    # file format version
    CAPABILITY_IMAGEPROC = 22    # capability of image processing


class DCIMG_PIXELTYPE(IntEnum):
    NONE = 0    # no pixeltype specified
    MONO8 = 1   # B/W 8 bit
    MONO16 = 2  # B/W 16 bit
    MONO32 = 4  # B/W 32 bit reserved


class DCIMG_CODEPAGE(IntEnum):
    SHIFT_JIS = 932    # Shift JIS
    UTF16_LE = 1200    # UTF-16 (Little Endian)
    UTF16_BE = 1201    # UTF-16 (Big Endian)
    UTF7 = 65000    # UTF-7 translation
    UTF8 = 65001    # UTF-8 translation


# ==== declare structures for DCIMG-API functions ====


class DCIMG_INIT(Structure):
    _pack_ = 8
    _fields_ = [
        ("size", c_int32),
        ("reserved", c_int32),
        ("guid", c_void_p)
    ]

    def __init__(self):
        self.size = sizeof(DCIMG_INIT)


class DCIMG_OPEN(Structure):
    _pack_ = 8
    _fields_ = [
        ("size", c_int32),
        ("codepage", c_int32),
        ("hdcimg", c_void_p),
        ("path", c_char_p)
    ]

    def __init__(self):
        self.size = sizeof(DCIMG_OPEN)


class DCIMG_TIMESTAMP(Structure):
    _pack_ = 8
    _fields_ = [
        ("sec", c_uint32),
        ("microsec", c_int32)
    ]

    def __init__(self):
        self.sec = 0
        self.microsec = 0


class DCIMG_FRAME(Structure):
    _pack_ = 8
    _fields_ = [
        ("size", c_int32),
        ("iKind", c_int32),
        ("option", c_int32),
        ("iFrame", c_int32),
        ("buf", c_void_p),
        ("rowbytes", c_int32),
        ("type", c_int32),    # DCIMG_PIXELTYPE
        ("width", c_int32),
        ("height", c_int32),
        ("left", c_int32),
        ("top", c_int32),
        ("timestamp", DCIMG_TIMESTAMP),
        ("framestamp", c_int32),
        ("camerastamp", c_int32)
    ]

    def __init__(self):
        self.size = sizeof(DCIMG_FRAME)
        self.iKind = 0
        self.option = 0
        self.iFrame = 0
        self.buf = 0
        self.rowbytes = 0
        self.type = DCIMG_PIXELTYPE.MONO16
        self.width = 0
        self.height = 0
        self.left = 0
        self.top = 0


# ==== assign aliases ====


def dcimg_init():
    __dll.dcimg_init.argtypes = [POINTER(DCIMG_INIT)]
    initparam = DCIMG_INIT()
    __dll.dcimg_init(byref(initparam))


dcimg_init()

# assign dcimg_open() argument
dcimg_open.argtypes = [POINTER(DCIMG_OPEN)]
# assign dcimg_getparaml() function
dcimg_getparaml = __dll.dcimg_getparaml
# assign dcimg_getparaml() argument
dcimg_getparaml.argtypes = [c_void_p, c_uint32, POINTER(c_int32)]
# assign dcimg_copyframe() function
dcimg_copyframe = __dll.dcimg_copyframe
# assign dcimg_copyframe() argument
dcimg_copyframe.argtypes = [c_void_p, POINTER(DCIMG_FRAME)]
# assign dcimg_close() function
dcimg_close = __dll.dcimg_close
# assign dcimg_close() argument
dcimg_close.argtypes = [c_void_p]


# ==== declare dcimg class ====


class Dcimg:
    """Control DCIMG-API.
    Class for instance to access DCIMG file.
    This handles the image data with Numpy.
    """
    # New instance
    def __init__(self):
        self.__hdcimg = c_void_p(None)
        self.__lasterr = DCIMG_ERR.SUCCESS
        self.__bOpened = False
        self.__image_width = 0
        self.__image_height = 0
        self.__image_pixeltype = 0
        self.__numberof_frame = 0
        self.__frame_index = -1
        self.__bRead = False
        self.__frame_buf = None

    def __repr__(self):
        return "dcimg()"

    def __str__(self):
        if not self.__bOpened:
            # DCIMG files is not opened
            return "<dcimg: None>"

        if self.__image_pixeltype == DCIMG_PIXELTYPE.MONO16:
            bpp = ",MONO16"
        elif self.__image_pixeltype == DCIMG_PIXELTYPE.MONO8:
            bpp = ",MONO8"
        else:
            bpp = ""

        return "<dcimg: %s of %s (height:%s,width:%s%s)>" % \
            (self.__frame_index, self.__numberof_frame,
             self.__image_height, self.__image_width, bpp)

    def failed(self):
        """Check the result of last called function.
        The result of last called function is stored to __lasterr member.
        When the value is minus, the result is error. Then this returns False.

        Returns:
            bool: True if __lasterr is error.
        """
        return self.__lasterr < 0

    def lasterr(self):
        """Return the result of last called function.
        Return __lasterr stored the result of last called function.

        Returns:
            DCIMG_ERR: return __lasterr
        """
        return self.__lasterr

    def open(self, path):
        """Open DCIMG file.
        Open DCIMG file specified by path.
        If dcimg_open() is failed, the error code is stored to __lasterr.

        Args:
            path (str): file path and name for DCIMG-File

        Returns:
            bool: result to open file
        """
        # close previous handle
        if self.__bOpened:
            dcimg_close(self.__hdcimg)

        # open DCIMG file
        imgopen = DCIMG_OPEN()
        imgopen.path = path.encode('UTF-8')
        imgopen.codepage = DCIMG_CODEPAGE.UTF8
        self.__lasterr = dcimg_open(byref(imgopen))

        if self.__lasterr < 0:
            # dcimg_open() was failed
            self.__hdcimg = c_void_p(None)
            self.__bOpened = False
            return False

        self.__hdcimg = imgopen.hdcimg
        self.__bOpened = True
        self.__image_width = self.getparaml(DCIMG_IDPARAML.IMAGE_WIDTH)
        self.__image_height = self.getparaml(DCIMG_IDPARAML.IMAGE_HEIGHT)
        self.__image_pixeltype = self.getparaml(DCIMG_IDPARAML.IMAGE_PIXELTYPE)
        self.__numberof_frame = self.getparaml(DCIMG_IDPARAML.NUMBEROF_FRAME)
        self.__frame_index = -1  # zero based
        self.__bRead = False
        return True

    def getparaml(self, idparaml):
        """Get information of opened file.
        Get value specified by idparaml.

        Args:
            idparaml (DCIMG_IDPARAML): parameter ID to get value

        Returns:
            int: value of parameter ID if success.
            bool: False if faiulre.
        """
        if not self.__bOpened:
            # divert
            self.__lasterr = DCIMG_ERR.FILENOTOPENED
            return False
        
        v = c_int32(0)
        self.__lasterr = dcimg_getparaml(self.__hdcimg, idparaml.value, byref(v))
        if self.failed():
            return False
        
        return v.value

    def image_width(self):
        """Return image width.
        Return horizontal column count of current image.

        Returns:
            int: return __image_width
        """
        return self.__image_width

    def image_height(self):
        """Return image height.
        Return vertical row count of current image.

        Returns:
            int: return __image_height
        """
        return self.__image_height

    def image_pixeltype(self):
        """Return PIXELTYPE.
        Return PIXELTYPE of current image.
        PIXELTYPE is defined in DCIMG_PIXELTYPE(IntEnum).

        Returns:
            int: return __image_pixeltype
        """
        return self.__image_pixeltype

    def frame_index(self):
        """Return index of current frame.
        Return frame index for last readframe() /readnext().
        The value is 0 based

        Returns:
            int: return __frame_index
        """
        return self.__frame_index

    def numberof_frame(self):
        """Return number of frames.
        Return number of frames in current session.

        Returns:
            int: return __numberof_frame
        """
        return self.__numberof_frame

    def isopened(self):
        """Check open flag.
        Return True when Dcimg file is opened.
        __bOpened is stored True when DCIMG file is opened.

        Returns:
            bool: return __bOpened        
        """
        return self.__bOpened

    def iseof(self):
        """Check end of file.
        Return True when DCIMG file is opened and the last frame is read.

        Returns:
            bool: True when the current frame is last frame.
        """
        return self.__bOpened and self.__numberof_frame <= self.__frame_index + 1

    def readframe(self, frameindex):
        """Read frame.
        Read the frame specified by frameindex.

        Args:
            frameindex (int): frame index

        Returns:
            NumPy ndarray: NumPy ndarray stored image if success
            bool: False if failure.
        """
        if not self.__bOpened:
            self.__lasterr = DCIMG_ERR.FILENOTOPENED
            return False

        if self.__image_pixeltype == DCIMG_PIXELTYPE.MONO16:
            self.__frame_buf = np.zeros((self.__image_height,
                                         self.__image_width),
                                        dtype='uint16')
            byteperpixel = 2
        elif self.__image_pixeltype == DCIMG_PIXELTYPE.MONO32:
            self.__frame_buf = np.zeros((self.__image_height,
                                         self.__image_width),
                                        dtype='int32')
            byteperpixel = 4
        elif self.__image_pixeltype == DCIMG_PIXELTYPE.MONO8:
            self.__frame_buf = np.zeros((self.__image_height,
                                         self.__image_width),
                                        dtype='uint8')
            byteperpixel = 1
        else:
            self.__lasterr = DCIMG_ERR.UNKNOWNFILEFORMAT
            return False

        imgframe = DCIMG_FRAME()
        imgframe.iFrame = frameindex
        imgframe.buf = self.__frame_buf.ctypes.data_as(c_void_p)
        imgframe.width = self.__image_width
        imgframe.height = self.__image_height
        imgframe.type = self.__image_pixeltype
        imgframe.rowbytes = self.__image_width * byteperpixel

        self.__lasterr = dcimg_copyframe(self.__hdcimg, byref(imgframe))
        if self.__lasterr < 0:
            return False

        self.__bRead = True
        self.__frame_index = imgframe.iFrame
        return self.__frame_buf

    def readnext(self):
        """Read next frame.
        Read next frame.

        Returns:
            NumPy ndarray: NumPy ndarray stored image if success
            bool: False if failure
        """
        if not self.__bOpened:
            self.__lasterr = DCIMG_ERR.FILENOTOPENED
            return False

        if not self.__frame_index + 1 < self.__numberof_frame:
            self.__lasterr = DCIMG_ERR.INVALIDFRAMEINDEX
            return False

        if self.__image_pixeltype == DCIMG_PIXELTYPE.MONO16:
            self.__frame_buf = np.zeros((self.__image_height,
                                         self.__image_width),
                                        dtype='uint16')
            byteperpixel = 2
        elif self.__image_pixeltype == DCIMG_PIXELTYPE.MONO32:
            self.__frame_buf = np.zeros((self.__image_height,
                                         self.__image_width),
                                        dtype='int32')
            byteperpixel = 4
        elif self.__image_pixeltype == DCIMG_PIXELTYPE.MONO8:
            self.__frame_buf = np.zeros((self.__image_height,
                                         self.__image_width),
                                        dtype='uint8')
            byteperpixel = 1
        else:
            self.__lasterr = DCIMG_ERR.UNKNOWNFILEFORMAT
            return False

        imgframe = DCIMG_FRAME()
        imgframe.iFrame = self.__frame_index + 1
        imgframe.buf = self.__frame_buf.ctypes.data_as(c_void_p)
        imgframe.width = self.__image_width
        imgframe.height = self.__image_height
        imgframe.rowbytes = self.__image_width * byteperpixel

        self.__lasterr = dcimg_copyframe(self.__hdcimg, byref(imgframe))
        if self.__lasterr < 0:
            return False

        self.__bRead = True
        self.__frame_index = imgframe.iFrame
        return self.__frame_buf
