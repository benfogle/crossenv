import os
from pathlib import Path
import shutil
import hashlib
import subprocess
import string
import copy
from distutils.dir_util import copy_tree
from collections import namedtuple

import pytest

from .testutils import ExecEnvironment, hash_file

Architecture = namedtuple('Architecture', 'name system machine')

ARCHITECTURES = [
    Architecture(
        name='aarch64-linux-musl',
        system='Linux',
        machine='aarch64',
    ),
    Architecture(
        name='arm-linux-musleabihf',
        system='Linux',
        machine='arm',
    ),
]

PY_VERSIONS = [
    '3.8.1',
]


PREBUILT_RESOURCES = {
    'build-python:3.8.1': {
        'source': 'prebuilt_musl_arm_aarch64.tar.xz',
        'binary': 'prebuilt_musl_arm_aarch64/python/3.8.1/build/bin/python3',
        'env': {
            'PATH': '$SOURCE/prebuilt_musl_arm_aarch64/musl-toolchain/bin:$PATH',
        },
    },
    'host-python:3.8.1:aarch64-linux-musl': {
        'source': 'prebuilt_musl_arm_aarch64.tar.xz',
        'binary': 'prebuilt_musl_arm_aarch64/python/3.8.1/aarch64/bin/python3',
        'env': {
            'QEMU_LD_PREFIX': '$SOURCE/prebuilt_musl_arm_aarch64/musl-toolchain/aarch64-linux-musl',
        }
    },
    'host-python:3.8.1:arm-linux-musleabihf': {
        'source': 'prebuilt_musl_arm_aarch64.tar.xz',
        'binary': 'prebuilt_musl_arm_aarch64/python/3.8.1/armhf/bin/python3',
        'env': {
            'QEMU_LD_PREFIX': '$SOURCE/prebuilt_musl_arm_aarch64/musl-toolchain/arm-linux-musleabihf',
        }
    },
    'hello-module:source': {
        'source': 'hello',
    },
}


class PrebuiltBlobs:
    def __init__(self):
        this_dir = Path(__file__).parent

        self.source_paths = [ this_dir/'prebuilt', this_dir/'sources' ]
        self.cache_dir = None
        self._existing_blobs = {}

    def get(self, source):
        path = self._existing_blobs.get(source)
        if path is not None:
            return path

        source = self.find_source(source)
        if source.is_file():
            return self.unpack_if_needed(source)
        elif source.is_dir():
            return source # Just use it in place.
        else:
            raise ValueError("Don't know how to use prebuilt {}".format(source))

    def find_source(self, source):
        for path in self.source_paths:
            result = path / source
            if result.exists():
                return result
        raise FileNotFoundError("No such file: {}".format(source))

    def unpack_if_needed(self, archive):
        if not self.cache_dir:
            raise ValueError("Need to configure cache_dir for prebuilt blobs!")
        digest = hash_file(archive)
        path = self.cache_dir / digest

        # Our caching check isn't real smart: if the directory exists,
        # then we'll assume everything is okay.
        if path.is_dir():
            return path

        path.mkdir(parents=True, exist_ok=False)
        try:
            shutil.unpack_archive(str(archive), str(path))
        except:
            shutil.rmtree(path)
            raise
        return path

prebuilt_blobs = PrebuiltBlobs()

class Resource(ExecEnvironment):
    def __init__(self, tag):
        super().__init__()

        try:
            info = PREBUILT_RESOURCES[tag]
        except KeyError:
            raise KeyError("No such resource {}".format(tag))

        try:
            self.source = info['source']
        except KeyError:
            raise KeyError(
                "Resource {} missing 'source' field".format(tag))

        self.path = prebuilt_blobs.get(self.source)
        self.binary = info.get('binary')
        if self.binary:
            self.binary = self.path / self.binary

        self.setenv('SOURCE', str(self.path))
        for name, value in info.get('env', {}).items():
            self.setenv(name, value)

        self._get_temp = None

    @classmethod
    def exists(cls, tag):
        return tag in PREBUILT_RESOURCES

    def make_copy(self, destdir = None, symlinks=True):
        if destdir is None:
            if self._get_temp is None:
                raise ValueError("Must explcitly set destdir")
            destdir = self._get_temp()

        new_env = copy.copy(self)
        new_env.path = destdir
        copy_tree(str(self.path),
                  str(destdir),
                  preserve_symlinks=symlinks)
        return new_env

@pytest.fixture(params=ARCHITECTURES, scope='session')
def architecture(request):
    return request.param

@pytest.fixture(params=PY_VERSIONS, scope='session')
def python_version(request):
    return request.param

@pytest.fixture(scope='session')
def build_python(python_version):
    build_python_tag = 'build-python:{}'.format(python_version)
    if not Resource.exists(build_python_tag):
        pytest.skip('No build-python version {} available'.format(
            python_version))

    return Resource(build_python_tag)

@pytest.fixture(scope='session')
def host_python(architecture, python_version):
    host_python_tag = 'host-python:{}:{}'.format(python_version, architecture.name)
    if not Resource.exists(host_python_tag):
        pytest.skip('No Python version {} available for {}'.format(
            python_version, architecture.name))

    return Resource(host_python_tag)

@pytest.fixture(scope='session')
def get_resource(tmp_path_factory):
    def _get_resource(tag):
        r = Resource(tag)
        r._get_temp = lambda: tmp_path_factory.mktemp('resource-copy')
        return r
    return _get_resource
