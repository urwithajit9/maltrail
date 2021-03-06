#!/usr/bin/env python

"""
Copyright (c) 2014-2015 Miroslav Stampar (@stamparm)
See the file 'LICENSE' for copying permission
"""

import os
import re
import socket
import stat
import subprocess

from core.attribdict import AttribDict

config = None
trails = {}

NAME = "Maltrail"
VERSION = "0.6"
SERVER_HEADER = "%s/%s" % (NAME, VERSION)
DATE_FORMAT = "%Y-%m-%d"
ROTATING_CHARS = ('\\', '|', '|', '/', '-')
TIMEOUT = 30
FRESH_LISTS_DELTA_DAYS = 2
USERS_DIRECTORY = os.path.join(os.path.expanduser("~"), ".%s" % NAME.lower())
TRAILS_FILE = os.path.join(USERS_DIRECTORY, "trails.csv")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
HTTP_DEFAULT_PORT = 8338
HTTP_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"  # Reference: http://stackoverflow.com/a/225106
SNAP_LEN = 2000
DEBUG = True  # show debug messages (in console output)
BLOCK_LENGTH = 1 + 2 + 4 + 4 + SNAP_LEN  # primitive mutex + short for packet size + int for sec + int for usec + max packet size
BUFFER_LENGTH = 512 * 1024 * 1024 / BLOCK_LENGTH * BLOCK_LENGTH  # 512MB buffer
SHORT_SENSOR_SLEEP_TIME = 0.00001
REGULAR_SENSOR_SLEEP_TIME = 0.001
LOAD_TRAILS_RETRY_SLEEP_TIME = 60
UNAUTHORIZED_SLEEP_TIME = 5
NO_SUCH_NAME_PER_HOUR_THRESHOLD = 30
NO_BLOCK = -1
END_BLOCK = -2
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HTML_DIR = os.path.join(ROOT_DIR, "html")
IPPROTO = 8
ETH_LENGTH = 14
CONFIG_FILE = os.path.join(ROOT_DIR, "maltrail.conf")
SYSTEM_LOG_DIRECTORY = "/var/log" if not subprocess.mswindows else "C:\\Windows\\Logs"
DEFAULT_LOG_PERMISSIONS = stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IROTH
HOSTNAME = socket.gethostname()
DISABLED_CONTENT_EXTENSIONS = (".py", ".pyc", ".md", ".txt", ".bak", ".conf", ".zip", "~")
LOW_PRIORITY_INFO_KEYWORDS = ("suspicious", "attacker", "abuser", "malicious", "dnspod")
BAD_TRAIL_PREFIXES = ("127.", "192.168.", "localhost")
SUSPICIOUS_DIRECT_DOWNLOAD_EXTENSIONS = set((".apk", ".exe", ".scr"))
SUSPICIOUS_FILENAMES = set(("gate.php",))
SUSPICIOUS_HTTP_REQUEST_REGEX = r"(?i)(information_schema|\b(AND|OR|SELECT)\b.*/\*.*\*/|/\*.*\*/.*\b(AND|OR|SELECT)\b|floor\(rand\(|order by \d+|sysdatabases|(\.\./){3,}|\bselect\b.*\bfrom\b.*\bwhere\b|\bselect \w+ from \w+|<script|\balert\(|xp_cmdshell|/etc/passwd|<\?php|boot\.ini|\bsleep\(|\bconvert\(|varchar|\bunion\s+(all\s+)?select\b)"
SUSPICIOUS_HTTP_REQUEST_FORCE_ENCODE_CHARS = "( )"
SESSIONS = {}
NO_SUCH_NAME_COUNTERS = {}  # this won't be (expensive) shared in multiprocessing run (hence, the threshold will effectively be n-times higher)
SESSION_ID_LENGTH = 16
SESSION_EXPIRATION_HOURS = 24 * 7
IPPROTO_LUT = dict(((getattr(socket, _), _.replace("IPPROTO_", "")) for _ in dir(socket) if _.startswith("IPPROTO_")))
DEFLATE_COMPRESS_LEVEL = 9
SUSPICIOUS_DOMAIN_LENGTH_THRESHOLD = 24
WHITELIST = set()

def _get_total_physmem():
    retval = None

    try:
        if subprocess.mswindows:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            c_ulong = ctypes.c_ulong
            class MEMORYSTATUS(ctypes.Structure):
                _fields_ = [
                    ('dwLength', c_ulong),
                    ('dwMemoryLoad', c_ulong),
                    ('dwTotalPhys', c_ulong),
                    ('dwAvailPhys', c_ulong),
                    ('dwTotalPageFile', c_ulong),
                    ('dwAvailPageFile', c_ulong),
                    ('dwTotalVirtual', c_ulong),
                    ('dwAvailVirtual', c_ulong)
                ]

            memory_status = MEMORYSTATUS()
            memory_status.dwLength = ctypes.sizeof(MEMORYSTATUS)
            kernel32.GlobalMemoryStatus(ctypes.byref(memory_status))

            retval = memory_status.dwTotalPhys
        else:
            retval = 1024 * int(re.search(r"(?i)MemTotal:\s+(\d+)\skB", open("/proc/meminfo").read()).group(1))
    except:
        pass

    if not retval:
        try:
            import psutil

            retval = psutil.phymem_usage().total
        except:
            pass

    return retval

def read_config():
    global BUFFER_LENGTH
    global config

    if not os.path.isfile(CONFIG_FILE):
        exit("[!] missing configuration file '%s'" % CONFIG_FILE)
    elif not config:
        config = AttribDict()

        try:
            array = None
            content = open(CONFIG_FILE, "rb").read()

            for line in content.split("\n"):
                line = re.sub(r"#.+", "", line)
                if not line.strip():
                    continue

                if line.count(' ') == 0:
                    array = line.upper()
                    config[array] = []
                    continue

                if array and line.startswith(' '):
                    config[array].append(line.strip())
                    continue
                else:
                    array = None
                    name, value = line = line.strip().split(' ', 1)
                    name = name.upper()
                    value = value.strip("'\"")

                if name.startswith("USE_"):
                    value = value.lower() in ("1", "true")
                elif value.isdigit():
                    value = int(value)
                else:
                    for match in re.finditer(r"\$([A-Z0-9_]+)", value):
                        if match.group(1) in globals():
                            value = value.replace(match.group(0), globals()[match.group(1)])
                        else:
                            value = value.replace(match.group(0), os.environ.get(match.group(1), match.group(0)))
                    if subprocess.mswindows and "://" not in value:
                        value = value.replace("/", "\\")

                config[name] = value

        except (IOError, OSError):
            pass

        for option in ("MONITOR_INTERFACE", "CAPTURE_BUFFER", "LOG_DIRECTORY"):
            if not option in config:
                exit("[!] missing mandatory option '%s' in configuration file '%s'" % (option, CONFIG_FILE))

        if config.CAPTURE_BUFFER:
            if config.CAPTURE_BUFFER.isdigit():
                BUFFER_LENGTH = int(config.CAPTURE_BUFFER)
            elif re.search(r"\d+%", config.CAPTURE_BUFFER):
                physmem = _get_total_physmem()

                if physmem:
                    BUFFER_LENGTH = physmem * int(re.search(r"(\d+)%", config.CAPTURE_BUFFER).group(1)) / 100
                else:
                    exit("[!] unable to determine total physical memory. Please use absolute value for 'CAPTURE_BUFFER'")

            BUFFER_LENGTH = BUFFER_LENGTH / BLOCK_LENGTH * BLOCK_LENGTH

def read_whitelist():
    WHITELIST.clear()

    _ = os.path.abspath(os.path.join(ROOT_DIR, "trails", "whitelist.txt"))
    if os.path.isfile(_):
        with open(_, "r") as f:
            for line in f.xreadlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                else:
                    WHITELIST.add(line)

if __name__ != "__main__":
    read_config()
    read_whitelist()
