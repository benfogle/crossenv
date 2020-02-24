import os
from pathlib import Path
import shutil
import hashlib

import pytest

from .resources import prebuilt_blobs

# Fixtures for everyone. Make sure to include fixture-of-fixture
# dependencies...
from .resources import host_python, build_python, architecture, \
        python_version, get_resource

def pytest_configure(config):
    # Make sure we use pathlib Paths, not pytest Paths
    cache_dir = Path(str(config.cache.makedir('prebuilt')))
    prebuilt_blobs.cache_dir = cache_dir

    # Set PYTHONPATH such that we can use crossenv wherever we are
    this_dir = Path(__file__).parent
    crossenv_dir = this_dir.parent.resolve()
    path = os.environ.get('PYTHONPATH')
    if path:
        path = str(crossenv_dir) + path
    else:
        path = str(crossenv_dir)
    os.environ['PYTHONPATH'] = path
