#!/usr/bin/env python

"""
Copyright (c) 2014-2015 Miroslav Stampar (@stamparm)
See the file 'LICENSE' for copying permission
"""

import glob
import os
import re

__url__ = "(custom)"
__reference__ = "(custom)"

def fetch():
    retval = {}

    for filename in glob.glob(os.path.join(os.path.dirname(__file__), "*.txt")):
        __info__ = os.path.splitext(os.path.basename(filename))[0].replace('_', " ")
        content = open(filename, "rb").read()
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '://' in line:
                line = re.search(r"://(.*)", line).group(1)
            line = line.rstrip('/')
            if '/' in line:
                retval[line] = (__info__, __reference__)
                line = line.split('/')[0]
            elif re.search(r"\A\d+\.\d+\.\d+\.\d+\Z", line):
                retval[line] = (__info__, __reference__)
            else:
                retval[line.strip('.')] = (__info__, __reference__)

    return retval
