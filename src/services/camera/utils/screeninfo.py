"""
Mock screeninfo module for testing.
"""


class Monitor:
    """Mock monitor object."""
    def __init__(self, width=1920, height=1080):
        self.width = width
        self.height = height


def get_monitors():
    """Return list of mock monitors."""
    return [Monitor(1920, 1080)]
