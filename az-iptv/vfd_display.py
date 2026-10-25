# -*- coding: utf-8 -*-
"""Front panel VFD display controller for Azamerica S1009+.

Azamerica S1009+ uses a PT6393 VFD controller driven by dvbapp.
The text buffer for the VFD is at memory address 0x016ab598,
and the C function to display a text string is at 0x0021c174.
"""

import os
import sys

VFD_TEXT_ADDR = 0x016ab598
FN_SET_TEXT = 0x0021c174


def set_display(text, logger=None):
    """Set the text shown on the front panel VFD display."""
    if not text:
        return False
    if isinstance(text, unicode):
        text = text.encode('ascii', 'ignore')
    
    # Clean up channel tags like [1080p FULL HD] or [720p HD] for display readability
    clean = text.split('[')[0].strip()
    clean = clean.replace('ao vivo', '').strip()
    if not clean:
        clean = text[:12]
    else:
        clean = clean[:12]

    # Method 1: ctypes direct C call to 0x0021c174
    try:
        import ctypes
        fn = ctypes.CFUNCTYPE(None, ctypes.c_char_p)(FN_SET_TEXT)
        fn(clean)
        if logger:
            logger('VFD set via ctypes to: %s' % clean)
        return True
    except Exception as e:
        if logger:
            logger('VFD ctypes failed: %s' % e)

    # Method 2: write to /proc/self/mem
    try:
        payload = clean.ljust(16, '\x00') + '\x00'
        with open('/proc/self/mem', 'r+b') as mem:
            mem.seek(VFD_TEXT_ADDR)
            mem.write(payload)
        if logger:
            logger('VFD set via /proc/self/mem to: %s' % clean)
        return True
    except Exception as e:
        if logger:
            logger('VFD /proc/self/mem failed: %s' % e)

    return False
