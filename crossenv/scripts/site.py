# Import only what we absolutely need before the path fixup
import importlib.machinery
import sys
import os

# sysconfig isn't _quite_ set up right, because it queries from a not-yet fixed
# sys module. The variables that come from build_time_vars are correct, so
# we can safely use those. We'll re-import it later once sys is fixed.
import sysconfig

# Fixup paths so we can import packages installed on the build
# system correctly.
sys.cross_compiling = 'crossenv'
sys.build_path = %(context.build_sys_path)r

abiflags = sysconfig.get_config_var('ABIFLAGS')
if abiflags is None:
    try:
        del sys.abiflags
    except AttributeError:
        pass
else:
    sys.abiflags = abiflags

stdlib = os.path.normpath(sysconfig.get_path('stdlib'))

class BuildPathFinder(importlib.machinery.PathFinder):
    """This class exists because we want to hide our modifications to
    sys.path so that pip/setuptools/etc. don't find build-python
    packages when deciding what to install."""
    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        if path is None:
            # Need to do this every time in case sys.path changes.
            # We insert build paths just before the host stdlibs
            path = []
            for i, p in enumerate(sys.path):
                if p.startswith(stdlib):
                    path.extend(sys.build_path)
                    path.extend(sys.path[i:])
                    break
                else:
                    path.append(p)
        return super().find_spec(fullname, path, target)

# Insert just before the regular sys.path handler
for i, meta in enumerate(sys.meta_path):
    if meta is importlib.machinery.PathFinder:
        sys.meta_path[i] = BuildPathFinder
        break
else:
    sys.meta_path.append(BuildPathFinder) #???

# Remove this directory. It's not needed after startup.
# The one after will be one of ours too.
cross_dir = os.path.dirname(__file__)
for index, p in enumerate(sys.path):
    if os.path.exists(p) and os.path.samefile(p, cross_dir):
        del sys.path[index:index+2]
        break


# A this point we can import more things
from configparser import ConfigParser
from collections import namedtuple
from functools import wraps
config = ConfigParser()
config.read(%(context.crossenv_cfg)r)

# Fixup sys:
# sysconfig should be correct, but some little parts of
# sys are hardcoded (but changable)
multiarch = sysconfig.get_config_var('MULTIARCH')
if multiarch is None:
    try:
        del sys.implementation._multiarch
    except AttributeError:
        pass
else:
    sys.implementation._multiarch = multiarch

# Fixup os.uname, which should fix most of platform module
uname_result_type = namedtuple('uname_result',
        'sysname nodename release version machine')
uname_result = uname_result_type(
        config.get('uname', 'sysname', fallback=''),
        config.get('uname', 'nodename', fallback=''),
        config.get('uname', 'release', fallback=''),
        config.get('uname', 'version', fallback=''),
        config.get('uname', 'machine', fallback=''))

@wraps(os.uname)
def uname():
    return uname_result
os.uname = uname

# Fixup platform
import platform
processor = config.get('uname', 'processor', fallback=None)
if processor is None:
    processor = config.get('uname', 'machine', fallback=None)
uname_result2 = platform.uname_result(
        config.get('uname', 'sysname', fallback=''),
        config.get('uname', 'nodename', fallback=''),
        config.get('uname', 'release', fallback=''),
        config.get('uname', 'version', fallback=''),
        config.get('uname', 'machine', fallback=''),
        processor)
@wraps(platform.uname)
def uname2():
    return uname_result2
platform.uname = uname2

if hasattr(platform, '_linux_distribution'):
    @wraps(platform._linux_distribution)
    def dist(*args, **kwargs):
        return ('', '', '')
    platform._linux_distribution = dist

@wraps(platform.libc_ver)
def libc_ver(*args, **kwargs):
    return ('', '')
platform.libc_ver = libc_ver

# importlib.reload would probably work, but just to be safe we'll try to 
# have the modules' __dict__ completely clean.
del sys.modules['site']
del sys.modules['sysconfig']
import site
import sysconfig
