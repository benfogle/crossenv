import os
from pathlib import Path
import shutil
import hashlib

import pytest

from .resources import prebuilt_blobs
from . import testutils

# Fixtures for everyone. Make sure to include fixture-of-fixture
# dependencies...
from .resources import host_python, build_python, architecture, \
        python_version, get_resource, crossenv_setup

def pytest_addoption(parser):
    parser.addoption('--coverage', action='store_true',
            help='Enable code coverage for crossenv')

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

@pytest.fixture(scope='module')
def crossenv(tmp_path_factory, host_python, build_python):
    """Convenience fixture for a per-module crossenv with default
    parameters."""
    tmp = tmp_path_factory.mktemp('crossenv')
    return testutils.make_crossenv(tmp, host_python, build_python)
