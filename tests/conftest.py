import os
from pathlib import Path
import shutil
import hashlib

import pytest

from .resources import prebuilt_blobs

# Fixtures for everyone. Make sure to include fixture-of-fixture
# dependencies...
from .resources import host_python, build_python, architecture, python_version

def pytest_configure(config):
    # Make sure we use pathlib Paths, not pytest Paths
    this_dir = Path(__file__).parent
    cache_dir = Path(str(config.cache.makedir('prebuilt')))
    prebuilt_blobs.cache_dir = cache_dir
    prebuilt_blobs.source_paths.append(this_dir / 'prebuilt')
