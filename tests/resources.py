import os
from pathlib import Path
import shutil
import hashlib
import copy
from textwrap import dedent
from collections import namedtuple

import pytest

from .testutils import ExecEnvironment, hash_file, open_lock_file

Architecture = namedtuple('Architecture', 'name system machine')
TestSetup = namedtuple('TestSetup',
        'name architecture version host_python_tag build_python_tag')

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
    Architecture(
        name='x86_64-linux-gnu',
        system='Linux',
        machine='x86_64',
    ),
]

PY_VERSIONS = [
    '3.8.1',
    '3.9.0',
    'main', # not always enabled
]

# This structure declares all the prebuilt resources we need. Each tag refers
# to a file or directory, that might need to be extracted. Really, we just
# unconditionally extract all archive sources defined below to the same $SOURCE
# directory before we begin. (We leave directory sources as-is.) Multiple
# resources can share a source archive: only one copy will be extracted.
#
# The binary attribute would be e.g., an executable to run. The env field is a
# dictionary specifying the environment needed to run it.
PREBUILT_RESOURCES = {
    'build-python:3.8.1': {
        'source': 'prebuilt_musl_arm_aarch64.tar.xz',
        'binary': 'prebuilt_musl_arm_aarch64/python/3.8.1/build/bin/python3',
        'env': {
            'PATH': '$SOURCE/prebuilt_musl_arm_aarch64/musl-toolchain/bin:$PATH',
        },
    },
    'host-python:3.8.1:x86_64-linux-gnu': {
        'source': 'prebuilt_musl_arm_aarch64.tar.xz',
        'binary': 'prebuilt_musl_arm_aarch64/python/3.8.1/build/bin/python3',
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
    'build-python:3.9.0': {
        'source': 'prebuilt_python3.9.0.tar.xz',
        'binary': 'prebuilt_python3.9.0/build/bin/python3',
        'env': {
            'PATH': '$SOURCE/prebuilt_musl_arm_aarch64/musl-toolchain/bin:$PATH',
        },
    },
    'host-python:3.9.0:x86_64-linux-gnu': {
        'source': 'prebuilt_python3.9.0.tar.xz',
        'binary': 'prebuilt_python3.9.0/build/bin/python3',
    },
    'host-python:3.9.0:aarch64-linux-musl': {
        'source': 'prebuilt_python3.9.0.tar.xz',
        'binary': 'prebuilt_python3.9.0/aarch64/bin/python3',
        'env': {
            'QEMU_LD_PREFIX': '$SOURCE/prebuilt_musl_arm_aarch64/musl-toolchain/aarch64-linux-musl',
        }
    },
    'host-python:3.9.0:arm-linux-musleabihf': {
        'source': 'prebuilt_python3.9.0.tar.xz',
        'binary': 'prebuilt_python3.9.0/armhf/bin/python3',
        'env': {
            'QEMU_LD_PREFIX': '$SOURCE/prebuilt_musl_arm_aarch64/musl-toolchain/arm-linux-musleabihf',
        }
    },
    # main is a bit of an anomaly: we don't pre build it. Instead we just
    # expect it to be there, and it's the test driver's responsibility to make
    # sure it's actually present. See prebuilt/src/CMakeLists.txt for help.
    # The main build is diabled by default anyway.
    'build-python:main': {
        'source': 'python/main/build',
        'binary': 'bin/python3',
        'env': {
            'PATH': '$EXTRACTED/prebuilt_musl_arm_aarch64/musl-toolchain/bin:$PATH',
        },
    },
    'host-python:main:x86_64-linux-gnu': {
        'source': 'python/main/build',
        'binary': 'bin/python3',
        'env': {
            'PATH': '$EXTRACTED/prebuilt_musl_arm_aarch64/musl-toolchain/bin:$PATH',
        },
    },
    'host-python:main:aarch64-linux-musl': {
        'source': 'python/main/aarch64',
        'binary': 'bin/python3',
        'env': {
            'QEMU_LD_PREFIX': '$EXTRACTED/prebuilt_musl_arm_aarch64/musl-toolchain/aarch64-linux-musl',
        },
    },
    'host-python:main:arm-linux-musleabihf': {
        'source': 'python/main/armhf',
        'binary': 'bin/python3',
        'env': {
            'QEMU_LD_PREFIX': '$EXTRACTED/prebuilt_musl_arm_aarch64/musl-toolchain/arm-linux-musleabihf',
        }
    },
    # All the same, but from a build directory.
    'build-python:main:obj': {
        'source': 'python-obj/main/build',
        'binary': 'python',
        'env': {
            'PATH': '$EXTRACTED/prebuilt_musl_arm_aarch64/musl-toolchain/bin:$PATH',
        },
    },
    'host-python:main:x86_64-linux-gnu:obj': {
        'source': 'python-obj/main/build',
        'binary': 'python',
        'env': {
            'PATH': '$EXTRACTED/prebuilt_musl_arm_aarch64/musl-toolchain/bin:$PATH',
        },
    },
    'host-python:main:aarch64-linux-musl:obj': {
        'source': 'python-obj/main/aarch64',
        'binary': 'python',
        'env': {
            'QEMU_LD_PREFIX': '$EXTRACTED/prebuilt_musl_arm_aarch64/musl-toolchain/aarch64-linux-musl',
            'LD_LIBRARY_PATH': '$SOURCE',
        },
    },
    'host-python:main:arm-linux-musleabihf:obj': {
        'source': 'python-obj/main/armhf',
        'binary': 'python',
        'env': {
            'QEMU_LD_PREFIX': '$EXTRACTED/prebuilt_musl_arm_aarch64/musl-toolchain/arm-linux-musleabihf',
            'LD_LIBRARY_PATH': '$SOURCE',
        }
    },

    # finally, source files
    'hello-module:source': {
        'source': 'hello',
    },
}


class PrebuiltBlobs:
    """We assume that all pre-built blobs defined in RESOURCES are needed,
    becuase we don't want to do dependency management. Everything that
    needs to be unpacked will be unpacked in the same directory. Everything
    that's already unpacked remains in place"""

    def __init__(self, resources):
        this_dir = Path(__file__).parent
        self.resources = resources
        self.source_paths = [ this_dir/'prebuilt', this_dir/'sources' ]
        self.extract_base = None
        self.cache_dir = None

        for tag, info in resources.items():
            if 'source' not in info:
                raise KeyError(
                    "Resource {} missing 'source' field".format(tag))


    def get(self, source):
        source = self.find_source(source)
        if source.is_file():
            return self.extract_dir
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

    @property
    def extract_dir(self):
        if not self.cache_dir:
            raise ValueError("Need to configure cache_dir for prebuilt blobs!")

        if not self.extract_base:
            # Find a hash-of-hash that will be our extraction directory. If
            # things change, we won't have a conflict.
            archives = set()
            for tag, info in self.resources.items():
                try:
                    src = self.find_source(info['source'])
                    if src.is_file():
                        archives.add(src)
                except FileNotFoundError:
                    pass

            digest = hashlib.sha256()
            for arc in sorted(archives):
                if arc.is_file():
                    digest.update(hash_file(arc).encode('ascii'))

            self.extract_base = digest.hexdigest()

        path = self.cache_dir / self.extract_base

        # we might have multiple runners via xdist, so lock
        # this
        lockfile = self.cache_dir / '.extracted.lock'
        with open_lock_file(lockfile) as lockpid:
            if lockpid is None:
                self._extract_all(path, archives)
        return path

    def _extract_all(self, path, archives):
        # Our caching check isn't real smart: if the directory exists,
        # then we'll assume everything is okay.
        if path.is_dir():
            return

        path.mkdir(parents=True, exist_ok=False)
        try:
            for arc in archives:
                shutil.unpack_archive(str(arc), str(path))
        except:
            shutil.rmtree(path)
            raise

prebuilt_blobs = PrebuiltBlobs(PREBUILT_RESOURCES)

class Resource(ExecEnvironment):
    """A container for running or accessing a particular resource"""

    def __init__(self, tag):
        super().__init__()

        try:
            info = prebuilt_blobs.resources[tag]
        except KeyError:
            raise KeyError("No such resource {}".format(tag))

        self.source = info['source']
        self.path = prebuilt_blobs.get(self.source)
        self.binary = info.get('binary')
        if self.binary:
            self.binary = self.path / self.binary

        self.setenv('SOURCE', str(self.path))
        self.setenv('EXTRACTED', str(prebuilt_blobs.extract_dir))
        for name, value in info.get('env', {}).items():
            self.setenv(name, value)

        self._get_temp = None

    @classmethod
    def exists(cls, tag):
        """Does this resource tag even exist?"""
        return tag in prebuilt_blobs.resources

    def make_copy(self, destdir = None, symlinks=True):
        """Make a copy of the file or directory"""
        if destdir is None:
            if self._get_temp is None:
                raise ValueError("Must explcitly set destdir")
            destdir = self._get_temp()

        new_env = copy.copy(self)
        new_env.path = destdir
        shutil.copytree(
            str(self.path),
            str(destdir),
            symlinks=symlinks
        )
        return new_env

    def derive(self):
        """A shallow copy that we can alter independently"""
        return copy.copy(self)

    def __repr__(self):
        return '<Resource {}>'.format(self.binary or self.path)

def collect_test_setups():
    # build_installed and host_installed, below, are causing us to hit some
    # issues with CI runners as the number of variants explodes. We'll leave
    # them disabled except for local tests, pending a later fix.
    if os.environ.get('CROSSENV_TEST_INPLACE'):
        installed = (True, False)
    else:
        installed = (True,)

    setups = []
    for version in PY_VERSIONS:
        for arch in ARCHITECTURES:
            for build_installed in installed:
                parts = ['build-python', version]
                if not build_installed:
                    parts.append('obj')
                build_python_tag = ':'.join(parts)
                if not Resource.exists(build_python_tag):
                    continue

                #for host_installed in (True, False):
                for host_installed in installed:
                    parts = ['host-python', version, arch.name]

                    if not host_installed:
                        parts.append('obj')
                    host_python_tag = ':'.join(parts)

                    if not Resource.exists(host_python_tag):
                        continue

                    build_installed = 'installed' if build_installed else 'inplace'
                    host_installed = 'installed' if host_installed else 'inplace'

                    name = ':'.join([arch.name, version, build_installed,
                        host_installed])
                    setups.append(TestSetup(name, arch, version,
                        host_python_tag, build_python_tag))
    return setups

@pytest.fixture(params=collect_test_setups(), scope='session', ids=lambda s: s.name)
def crossenv_setup(request):
    return request.param

@pytest.fixture(scope='session')
def architecture(crossenv_setup):
    return crossenv_setup.architecture

@pytest.fixture(scope='session')
def python_version(crossenv_setup):
    return crossenv_setup.version

def setup_coverage(venv_python):
    """Get code coverage, if requested. This is tricker than normal, because
    we're gathering coverage for a completely different interpreter than the
    one that is driving the tests.

    This covers the creation of crossenv, and nothing after that."""

    # Install coverage, make it active automatically
    python = venv_python.binary
    venv_python.check_call([python, '-m', 'pip', 'install', 'coverage'])
    site_packages = Path(venv_python.check_output([python, '-c',
        'import site; print(site.getsitepackages()[0])'],
        universal_newlines=True).strip())
    with open(site_packages / 'cov.pth', 'w') as fp:
        fp.write('import coverage; coverage.process_startup()\n')

    # Configure coverage
    coverage_file = Path('./.coverage').resolve() # output in cwd

    coverage_config = venv_python.path / '.coveragerc'
    with open(coverage_config, 'w') as fp:
        fp.write(dedent('''\
            [run]
            branch = True
            source = crossenv
            data_file = {}
            parallel = True
            '''.format(coverage_file)))

    # Enable it
    venv_python.setenv('COVERAGE_PROCESS_START', coverage_config.resolve())

@pytest.fixture(scope='session')
def build_python(request, crossenv_setup, tmp_path_factory):
    build_python_tag = crossenv_setup.build_python_tag
    try:
        base = Resource(build_python_tag)
    except KeyError:
        pytest.skip('No build-python version {} available'.format(
            crossenv_setup.version))
    except FileNotFoundError:
        pytest.skip('Build-python version {} registerd, but not found on '
                'disk'.format(crossenv_setup.version))

    # Make a virtualenv for build-python. This is not necessary for the tests,
    # but it lets us install coverage and other support packages so we can
    # measure code coverage while we are creating the environment
    python = base.binary
    venv = tmp_path_factory.mktemp('build-venv')
    base.check_call([python, '-m', 'venv', venv])

    venv_python = base.derive()
    venv_python.path = venv
    venv_python.binary = venv / 'bin' / 'python'
    if request.config.getoption('--coverage'):
        setup_coverage(venv_python)
    return venv_python

@pytest.fixture(scope='session')
def host_python(crossenv_setup):
    host_python_tag = crossenv_setup.host_python_tag
    try:
        return Resource(host_python_tag)
    except KeyError:
        pytest.skip('No Python version {} available for {}'.format(
            crossenv_setup.version, crossenv_setup.architecture.name))
    except FileNotFoundError:
        pytest.skip('Python version {} for {} registerd, but not found on '
            'disk'.format(crossenv_setup.version, crossenv_setup.architecture.name))


@pytest.fixture(scope='session')
def get_resource(tmp_path_factory):
    def _get_resource(tag):
        r = Resource(tag)
        r._get_temp = lambda: tmp_path_factory.mktemp('resource-copy')
        return r
    return _get_resource
