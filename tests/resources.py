import os
from pathlib import Path
import shutil
import hashlib
import subprocess
import string

import pytest

PREBUILT_RESOURCES = {
    'build-python:3.8.1': {
        'source': 'prebuilt_musl_arm_aarch64.tar.xz',
        'binary': 'prebuilt_musl_arm_aarch64/python/3.8.1/build/bin/python3',
        'env': {
            'PATH': '{SOURCE}/prebuilt_musl_arm_aarch64/musl-toolchain/bin:$PATH',
        },
    },
    'host-python:3.8.1:aarch64-linux-musl': {
        'source': 'prebuilt_musl_arm_aarch64.tar.xz',
        'binary': 'prebuilt_musl_arm_aarch64/python/3.8.1/aarch64/bin/python3',
        'env': {
            'QEMU_LD_PREFIX': '{SOURCE}/prebuilt_musl_arm_aarch64/musl-toolchain/aarch64-linux-musl',
        }
    },
    'host-python:3.8.1:arm-linux-musleabihf': {
        'source': 'prebuilt_musl_arm_aarch64.tar.xz',
        'binary': 'prebuilt_musl_arm_aarch64/python/3.8.1/armhf/bin/python3',
        'env': {
            'QEMU_LD_PREFIX': '{SOURCE}/prebuilt_musl_arm_aarch64/musl-toolchain/arm-linux-musleabihf',
        }
    },
}

def hash_file(path):
    ctx = hashlib.sha256()
    with open(path, 'rb') as fp:
        data = fp.read(0x4000)
        while data:
            ctx.update(data)
            data = fp.read(0x4000)
    return ctx.hexdigest()

class PrebuiltBlobs:
    def __init__(self):
        self.source_paths = []
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
            if result.exists:
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

class Resource:
    def __init__(self, source, binary=None, env=None):
        self.source = source
        self.path = prebuilt_blobs.get(source)
        if binary is not None:
            binary = (self.path / binary).resolve()
        self.binary = binary
        env = env or {}
        self.env = {}

        for name, value in env.items():
            value = value.format(SOURCE=self.path.resolve())
            self.env[name] = value


    def _popen(self, func, *args, **kwargs):
        env = kwargs.get('env')
        if env is None:
            env = os.environ.copy()
        else:
            env = env.copy()

        # os.path.expandvars exists, but doesn't operate on an arbitrary
        # environment. We might clobber changes to $PATH, etc. if we use
        # it.
        class EnvDict:
            def __init__(self, src):
                self.src = src
            def __getitem__(self, key):
                return self.src.get(key, '')

        new_env = {}
        for name, value in self.env.items():
            value = string.Template(value).substitute(EnvDict(env))
            new_env[name] = value

        env.update(new_env)
        kwargs['env'] = env

        return func(*args, **kwargs)


    def run(self, *args, **kwargs):
        return self._popen(subprocess.run, *args, **kwargs)


    def popen(self, *args, **kwargs):
        return self._popen(subprocess.Popen, *args, **kwargs)


    def check_call(self, *args, **kwargs):
        return self._popen(subprocess.check_call, *args, **kwargs)


    def check_output(self, *args, **kwargs):
        return self._popen(subprocess.check_output, *args, **kwargs)

ARCHITECTURES = [
    'aarch64-linux-musl',
    'arm-linux-musleabihf',
]

PY_VERSIONS = [
    '3.8.1',
]

@pytest.fixture(params=ARCHITECTURES)
def architecture(request):
    return request.param

@pytest.fixture(params=PY_VERSIONS)
def python_version(request):
    return request.param

@pytest.fixture
def build_python(python_version):
    build_python_tag = 'build-python:{}'.format(python_version)
    build_python = Resource(**PREBUILT_RESOURCES[build_python_tag])

    if build_python_tag not in PREBUILT_RESOURCES:
        pytest.skip('No build-python version {} available'.format(
            python_version))

    build_python = Resource(**PREBUILT_RESOURCES[build_python_tag])
    return build_python

@pytest.fixture
def host_python(architecture, python_version):
    host_python_tag = 'host-python:{}:{}'.format(python_version, architecture)

    if host_python_tag not in PREBUILT_RESOURCES:
        pytest.skip('No Python version {} available for {}'.format(
            python_version, architecture))

    host_python = Resource(**PREBUILT_RESOURCES[host_python_tag])
    return host_python
