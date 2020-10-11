import venv
import os
import sysconfig
import glob
import sys
import shutil
from textwrap import dedent
import subprocess
import logging
import importlib
import types
from configparser import ConfigParser
import random
import shlex
import platform
import pprint
import re

from .utils import F
from . import utils

__version__ = '1.0'

logger = logging.getLogger(__name__)

class CrossEnvBuilder(venv.EnvBuilder):
    """
    A class to build a cross-compiling virtual environment useful for
    cross compiling wheels or developing firmware images.

    Here the `host` is the device on which the final code will run, such
    as an embedded system of some sort. `build` is the machine doing the
    compiling, usually a desktop or server. Usually the `host` Python
    executables won't run on the `build` machine.

    When we refer to `build-python`, we mean the current interpreter.  (It is
    *always* the current interpreter.) When we refer to `host-pytohn`, we mean
    the interpreter that will run on the host. When we refer to `cross-python`,
    we mean an interpreter that runs on `build` but reports system information
    as if it were running on `host`. In other words, `cross-python` does the
    cross compiling, and is what this class will create for us.

    You must have the toolchain used to compile the host Python binary
    available when using this virtual environment. The virtual environment
    will pick the correct compiler based on info recorded when the host
    Python binary was compiled.

    :param host_python:     The path to the host Python binary. This may be in
                            a build directory (i.e., after `make`), or in an
                            install directory (after `make install`).  It
                            *must* be the exact same version as build-python.

    :param extra_env_vars:  When cross-python starts, this is an iterable of
                            (name, op, value) tuples. op may be one of '=' to
                            indicate that the variable will be set
                            unconditionally, or '?=' to indicate that the
                            variable will be set only if not already set by the
                            environment.

    :param build_system_site_packages:
                            Whether or not build-python's virtual environment
                            will have access to the system site packages.
                            cross-python never has access, for obvious reasons.

    :param clear:           Whether to delete the contents of the environment
                            directories if they already exist, before
                            environment creation. May be a false value, or one
                            of 'default', 'cross', 'build', or 'both'.
                            'default' means to clear cross only when
                            cross_prefix is None.

    :param cross_prefix:    Explicitly set the location of the cross-python
                            virtual environment.

    :param with_cross_pip:  If True, ensure pip is installed in the
                            cross-python virtual environment.

    :param with_build_pip:  If True, ensure pip is installed in the
                            build-python virtual environment.

    :param host_sysroot:    If given, the cross-compiler toolchain's sysroot.
                            If not given, an attempt will be made to guess.
                            These will be added (redundantly) to the default
                            search paths to help trick some packages.

    :param host_cc:         If given, override CC and related variables with
                            this value.

    :param host_cxx:        If given, override CXX and related variables with
                            this value.

    :param host_ar:         If given, override AR and related variables with
                            this value.

    :param host_relativize: If True, convert absolute paths in CC, CXX, and
                            related variables to use the base name. Tools must
                            be in $PATH for this to work.
    :param host_config_vars:    Extra config_vars (build_time_vars) to override,
                                such as CC, CCSHARED, etc.
    :param host_sysconfigdata_file:  Explicitly set the sysconfigdata file path.
                                     If not given, all sysconfigdata files will
                                     be searched and will error if there are
                                     multiple files that have different values.
    """
    def __init__(self, *,
            host_python,
            extra_env_vars=(),
            build_system_site_packages=False,
            clear=False,
            cross_prefix=None,
            with_cross_pip=False,
            with_build_pip=False,
            host_sysroot=None,
            host_cc=None,
            host_cxx=None,
            host_ar=None,
            host_relativize=False,
            host_config_vars=(),
            host_sysconfigdata_file=None):
        self.host_sysroot = host_sysroot
        self.host_cc = None
        self.host_cxx = None
        self.host_ar = None
        if host_cc:
            self.host_cc = shlex.split(host_cc)
        if host_cxx:
            self.host_cxx = shlex.split(host_cxx)
        if host_ar:
            self.host_ar = shlex.split(host_ar)
        self.host_relativize = host_relativize
        self.host_config_vars = host_config_vars
        self.host_sysconfigdata_file = host_sysconfigdata_file
        self.build_system_site_packages = build_system_site_packages
        self.extra_env_vars = extra_env_vars
        self.clear_build = clear in ('default', 'build', 'both')
        if with_cross_pip and not with_build_pip:
            raise ValueError("Cannot have cross-pip without build-pip")
        self.with_cross_pip = with_cross_pip
        self.with_build_pip = with_build_pip
        if cross_prefix:
            self.cross_prefix = os.path.abspath(cross_prefix)
            self.clear_cross = clear in ('cross', 'both')
        else:
            self.cross_prefix = None
            self.clear_cross = clear in ('default', 'cross', 'both')

        self.find_host_python(host_python)
        self.find_compiler_info()

        super().__init__(
                system_site_packages=False,
                clear=False,
                symlinks=True,
                upgrade=False,
                with_pip=False)


    def find_installed_host_home(self):
        # Assume host_project_base == {prefix}/bin and that this Python
        # mirrors the host Python's install paths.
        # On caveat: on native host Python (for testing) this might be a
        # virtualenv.
        home = os.path.dirname(self.host_project_base)
        pyvenv = os.path.join(home, 'pyvenv.cfg')
        if os.path.exists(pyvenv):
            with open(pyvenv) as fp:
                for line in fp:
                    key, _, val = line.partition('=')
                    key = key.strip()
                    val = val.strip()
                    if key == 'home':
                        return os.path.dirname(val)
        return home

    def find_sysconfig_data(self, paths):
        maybe = []
        for path in paths:
            pattern = os.path.join(path, '_sysconfigdata*.py*')
            maybe.extend(glob.glob(pattern))

        sysconfig_paths = set()
        for filename in maybe:
            if (os.path.isfile(filename) and
                    os.path.splitext(filename)[1] in ('.py', '.pyc')):
                sysconfig_paths.add(filename)

        # Multiples can happen, but so long as they all have the same
        # info we should be okay. Seen in buildroot
        # When choosing the correct one, prefer, in order:
        #   1) The .py file
        #   2) The .pyc file
        #   3) Any .opt-*.pyc files
        # so sort by the length of the longest extension
        sysconfig_paths = sorted(sysconfig_paths,
                                 key=lambda x: len(x.split('.',1)[1]))
        if self.host_sysconfigdata_file is not None:
            sysconfig_paths = [self.host_sysconfigdata_file]
        self.host_sysconfigdata = None
        for path in sysconfig_paths:
            basename = os.path.basename(path)
            name, _ = os.path.splitext(basename)
            spec = importlib.util.spec_from_file_location(name, path)
            syscfg = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(syscfg)
            if self.host_sysconfigdata is None:
                self.host_sysconfigdata = syscfg
                self.host_sysconfigdata_file = path
                self.host_sysconfigdata_name = name
            elif (self.host_sysconfigdata.build_time_vars !=
                    syscfg.build_time_vars):
                logger.error("Conflicting build info in %s and %s",
                        self.host_sysconfigdata_file, path)
                raise ValueError("Malformed Python installation!")

        if not self.host_sysconfigdata:
            logger.error("Cannot find _sysconfigdata*.py. Looked in %s",
                    ', '.join(paths))
            raise FileNotFoundError("No _sysconfigdata*.py found in host lib")


    def find_host_python(self, host):
        """
        Find Python paths and other info based on a path.

        :param host:    Path to the host Python executable.
        """

        build_version = sysconfig.get_config_var('VERSION')
        host = os.path.abspath(host)
        if not os.path.exists(host):
            raise FileNotFoundError("%s does not exist" % host)
        elif not os.path.isfile(host):
            raise ValueError("Expected a path to a Python executable. "
                             "Got %s" % host)
        else:
            self.host_project_base = os.path.dirname(host)

        if sysconfig._is_python_source_dir(self.host_project_base):
            self.host_makefile = os.path.join(self.host_project_base, 'Makefile')
            pybuilddir = os.path.join(self.host_project_base, 'pybuilddir.txt')
            try:
                with open(pybuilddir, 'r') as fp:
                    build_dir = fp.read().strip()
            except IOError:
                raise IOError(
                    "Cannot read %s: Build the host Python first " % s) from None

            self.host_home = self.host_project_base
            sysconfig_paths = [os.path.join(self.host_project_base, build_dir)]
        else:
            self.host_home = self.find_installed_host_home()
            python_ver = 'python' + sysconfig.get_config_var('py_version_short')
            libdir = os.path.join(self.host_home, 'lib', python_ver)
            sysconfig_paths = [
                libdir,
                # Ubuntu puts it in libdir/plat-<arch>
                os.path.join(libdir, '*'),
                # Below might be a version mismatch, but try to use it
                #os.path.join(self.host_home, 'lib', 'python*'),
                #os.path.join(self.host_home, 'lib', 'python*', '*'),
            ]

            makefile = glob.glob(os.path.join(libdir, '*', 'Makefile'))
            if not makefile:
                self.host_makefile = '' # fail later
            else:
                self.host_makefile = makefile[0]


        # We need paths to sysconfig data, and we need to import it to ask
        # a few questions.
        self.find_sysconfig_data(sysconfig_paths)

        # If the user wants to override host_cc, that takes precedence.
        host_cc = self.host_sysconfigdata.build_time_vars['CC']
        self.real_host_cc = shlex.split(host_cc)
        if not self.host_cc:
            self.host_cc = self.real_host_cc
            if self.host_relativize:
                self.host_cc[0] = os.path.basename(self.host_cc[0])

        # CC could be compound command, like 'gcc --sysroot=...' (Issue #5)
        # but that can cause issues (#7) so let the user know.
        if len(self.host_cc) > 1:
            logger.warning("CC is a compound command (%s)", self.host_cc)
            logger.warning("This can cause issues for modules that don't "
                           "expect it.")
            logger.warning("Consider setting CC='%s' and CFLAGS='%s'",
                    self.host_cc[0], ' '.join(self.host_cc[1:]))

        host_cxx = self.host_sysconfigdata.build_time_vars['CXX']
        self.real_host_cxx = shlex.split(host_cxx)
        if not self.host_cxx:
            self.host_cxx = self.real_host_cxx
            if self.host_relativize:
                self.host_cxx[0] = os.path.basename(self.host_cxx[0])

        if len(self.host_cxx) > 1:
            logger.warning("CXX is a compound command (%s)", self.host_cxx)
            logger.warning("This can cause issues for modules that don't "
                           "expect it.")
            logger.warning("Consider setting CXX='%s' and CXXFLAGS='%s'",
                    self.host_cxx[0], ' '.join(self.host_cxx[1:]))

        host_ar = self.host_sysconfigdata.build_time_vars['AR']
        self.real_host_ar = shlex.split(host_ar)
        if not self.host_ar:
            self.host_ar = self.real_host_ar
            if self.host_relativize:
                self.host_ar[0] = os.path.basename(self.host_ar[0])

        self.host_version = self.host_sysconfigdata.build_time_vars['VERSION']

        # Ask the makefile a few questions too
        if not os.path.exists(self.host_makefile):
            raise FileNotFoundError("Cannot find Makefile")

        self.host_platform = sys.platform # Default: not actually cross compiling
        with open(self.host_makefile, 'r') as fp:
            lines = list(fp.readlines())

        for line in lines:
            line = line.strip()
            if line.startswith('_PYTHON_HOST_PLATFORM='):
                host_platform = line.split('=',1)[-1]
                if host_platform:
                    self.host_platform = line.split('=',1)[-1]
                break

        self.macosx_deployment_target = ''
        for line in lines:
            line = line.strip()
            if line.startswith('MACOSX_DEPLOYMENT_TARGET='):
                self.macosx_deployment_target = line.split('=',1)[-1]
                break

        # Sanity checks
        if self.host_version != build_version:
            raise ValueError("Version mismatch: host=%s, build=%s" % (
                self.host_version, build_version))

    def find_compiler_info(self):
        """
        Query the compiler for extra info useful for cross-compiling,
        and also check that it exists.
        """

        def run_compiler(arg):
            cmdline = self.host_cc + [arg]
            try:
                return subprocess.check_output(cmdline, universal_newlines=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                return None

        if run_compiler('--version') is None:
            # I guess we could continue...but why?
            raise RuntimeError(
                "Cannot run cross-compiler (%r)! Extension modules won't "
                "build! Use --cc to correct." % ' '.join(self.host_cc))
            return

        # TODO: Clang doesn't have this option
        if self.host_sysroot is None:
            self.host_sysroot = run_compiler('-print-sysroot')
            if self.host_sysroot:
                self.host_sysroot = self.host_sysroot.strip()

        # Sanity check that this is the right compiler. (See #24, #27.)
        found_triple = run_compiler('-dumpmachine').strip().strip()
        if found_triple:
            expected = self.host_sysconfigdata.build_time_vars['HOST_GNU_TYPE']
            if not self._compare_triples(found_triple, expected):
                logger.warning("The cross-compiler (%r) does not appear to be "
                               "for the correct architecture (got %s, expected "
                               "%s). Use --cc to correct, if necessary.",
                               ' '.join(self.host_cc),
                               found_triple,
                               expected)

    def _compare_triples(self, x, y):
        # They are in the form cpu-vendor-kernel-system or cpu-kernel-system.
        # So we'll get something like: x86_64-linux-gnu or x86_64-pc-linux-gnu.
        # We won't overcomplicate this, since it's just to generate a warning.
        #
        # We return True if we can't make sense of anything and wish to skip
        # the warning.

        parts_x = x.split('-')
        if len(parts_x) == 4:
            del parts_x[1]
        elif len(parts_x) != 3:
            return True # Some other form? Bail out.

        parts_y = y.split('-')
        if len(parts_y) == 4:
            del parts_y[1]
        elif len(parts_y) != 3:
            return True # Some other form? Bail out.

        return parts_x == parts_y


    def create(self, env_dir):
        """
        Create a cross virtual environment in a directory

        :param env_dir: The target directory to create an environment in.
        """

        env_dir = os.path.abspath(env_dir)
        context = self.ensure_directories(env_dir)
        self.create_configuration(context)
        self.make_build_python(context)
        self.make_cross_python(context)
        self.post_setup(context)

    def ensure_directories(self, env_dir):
        """
        Create the directories for the environment.

        Returns a context object which holds paths in the environment,
        for use by subsequent logic.
        """

        # Directory structure:
        #
        # ENV_DIR/
        #   cross/      cross-python venv
        #   build/      build-python venv
        #   lib/        libs for setting up cross-python
        #   bin/        holds activate scripts.

        if os.path.exists(env_dir) and (self.clear_cross or self.clear_build):
            subdirs = os.listdir(env_dir)
            for sub in subdirs:
                if sub in ('cross', 'build'):
                    continue
                utils.remove_path(os.path.join(env_dir, sub))

        context = super().ensure_directories(env_dir)
        context.lib_path = os.path.join(env_dir, 'lib')
        context.exposed_libs = os.path.join(context.lib_path, 'exposed.txt')
        utils.mkdir_if_needed(context.lib_path)
        return context

    def create_configuration(self, context):
        """
        Create configuration files. We don't have a pyvenv.cfg file in the
        base directory, but we do have a uname crossenv.cfg file.
        """

        # Do our best to guess defaults
        config = ConfigParser()
        # host_platform is _probably_ something like linux-x86_64, but it can
        # vary.
        host_info = self.host_platform.split('-')
        if not host_info:
            sysname = sys.platform
        elif len(host_info) == 1:
            sysname = host_info[0]
            machine = platform.machine()
        else:
            sysname = host_info[0]
            machine = host_info[-1]

        release = ''
        if self.macosx_deployment_target:
            try:
                major, minor = self.macosx_deployment_target.split(".")
                major, minor = int(major), int(minor)
            except ValueError:
                raise ValueError("Unexpected value %s for MACOSX_DEPLOYMENT_TARGET" %
                        self.macosx_deployment_target)
            if major == 10:
                release = "%s.0.0" % (minor + 4)
            elif major == 11:
                release = "%s.0.0" % (minor + 20)
            else:
                raise ValueError("Unexpected major version %s for MACOSX_DEPLOYMENT_TARGET" %
                        major)

        config['uname'] = {
            'sysname' : sysname.title(),
            'nodename' : 'build',
            'release' : release,
            'version' : '',
            'machine' : machine,
        }

        context.crossenv_cfg = os.path.join(context.env_dir, 'crossenv.cfg')
        with utils.overwrite_file(context.crossenv_cfg) as fp:
            config.write(fp)

    def make_build_python(self, context):
        """
        Assemble the build-python virtual environment
        """

        context.build_env_dir = os.path.join(context.env_dir, 'build')
        logger.info("Creating build-python environment")
        env = venv.EnvBuilder(
                system_site_packages=self.build_system_site_packages,
                clear=self.clear_build,
                with_pip=self.with_build_pip)
        env.create(context.build_env_dir)
        context.build_bin_path = os.path.join(context.build_env_dir, 'bin')
        context.build_env_exe = os.path.join(
                context.build_bin_path, context.python_exe)

        # What is build-python's sys.path?
        out = subprocess.check_output(
                [context.build_env_exe,
                    '-c',
                    r"import sys; print('\n'.join(sys.path))"],
                universal_newlines=True).splitlines()
        context.build_sys_path = []
        for line in out:
            line = line.strip()
            if line:
                context.build_sys_path.append(line)

        if self.with_build_pip:
            # Make sure we install the same version of pip and setuptools to
            # prevent errors (#1).
            reqs = subprocess.check_output([context.build_env_exe, '-m', 'pip',
                '--disable-pip-version-check',
                'freeze',
                '--all'],
                universal_newlines=True)
            all_reqs = reqs.split()
            context.build_pip_reqs = []
            for req in all_reqs:
                package = req.split('==')[0]
                if package == 'pip':
                    context.build_pip_version = req
                    context.build_pip_reqs.append(req)
                elif package == 'setuptools':
                    context.build_pip_reqs.append(req)

            # Many distributions use a patched, 'unbundled' version of pip,
            # where the vendored packages aren't stored within pip itself, but
            # elsewhere on the system. This breaks cross-pip, which won't be
            # able to find them after the modifications we made. Fix this by
            # downloading a stock version of pip (Issue #6).
            if self._build_pip_is_unbundled(context):
                logger.info("Redownloading stock pip")
                subprocess.check_output([context.build_env_exe, '-m', 'pip',
                    '--disable-pip-version-check',
                    'install',
                    '--ignore-installed',
                    context.build_pip_version])

    def _build_pip_is_unbundled(self, context):
        pyver = 'python' + sysconfig.get_config_var('py_version_short')
        bundled_module = os.path.join(context.build_env_dir,
                              'lib',
                              pyver,
                              'site-packages',
                              'pip',
                              '_vendor',
                              'six.py')
        return not os.path.exists(bundled_module)

    def make_cross_python(self, context):
        """
        Assemble the cross-python virtual environment
        """

        logger.info("Creating cross-python environment")
        if self.cross_prefix:
            context.cross_env_dir = self.cross_prefix
        else:
            context.cross_env_dir = os.path.join(context.env_dir, 'cross')
        clear_cross = self.clear in ('default', 'cross-only', 'both')
        env = venv.EnvBuilder(
                system_site_packages=False,
                clear=self.clear_cross,
                symlinks=True,
                upgrade=False,
                with_pip=False)
        env.create(context.cross_env_dir)
        context.cross_bin_path = os.path.join(context.cross_env_dir, 'bin')
        context.cross_env_exe = os.path.join(
                context.cross_bin_path, context.python_exe)
        context.cross_cfg_path = os.path.join(context.cross_env_dir, 'pyvenv.cfg')
        context.cross_activate = os.path.join(context.cross_bin_path, 'activate')

        # Remove binaries. We'll run from elsewhere
        for exe in os.listdir(context.cross_bin_path):
            if not exe.startswith('activate'):
                utils.remove_path(os.path.join(context.cross_bin_path, exe))

        # Alter pyvenv.cfg
        with utils.overwrite_file(context.cross_cfg_path) as out:
            with open(context.cross_cfg_path) as inp:
                for line in inp:
                    if line.split()[0:2] == ['home', '=']:
                        line = 'home = %s\n' % self.host_project_base
                    out.write(line)

        # make a script that sets the environment variables and calls Python.
        # Don't do this in bin/activate, because it's a pain to set/unset
        # properly (and for csh, fish as well).

        # Note that env_exe hasn't actually been created yet.

        sysconfig_name = os.path.basename(self.host_sysconfigdata_file)
        sysconfig_name, _ = os.path.splitext(sysconfig_name)

        # If this venv is generated from a cross-python still in its
        # build directory, rather than installed, then our modifications
        # prevent build-python from finding its pure-Python libs, which
        # will cause a crash on startup. Add them back to PYTHONPATH.
        # Also: 'stdlib' might not be accurate if build-python is in a build
        # directory.
        stdlib = os.path.abspath(os.path.dirname(os.__file__))

        context.sentinel = random.randint(0,0xffffffff)

        extra_envs = list(self.extra_env_vars)

        # Add sysroot to various environment variables. This doesn't help
        # compiling, but some packages try to do manual checks for existence
        # of headers and libraries. This will help them find things.
        if self.host_sysroot:
            if os.path.isdir(os.path.join(self.host_sysroot, 'usr')):
                libs = os.path.join(self.host_sysroot, 'usr', 'lib*')
                inc = os.path.join(self.host_sysroot, 'usr', 'include')
            elif os.path.isdir(os.path.join(self.host_sysroot, 'lib')):
                libs = os.path.join(self.host_sysroot, 'lib*')
                inc = os.path.join(self.host_sysroot, 'include')
            else:
                libs = ''
                inc = ''

            libs = glob.glob(libs)
            if not libs:
                logger.warning("No libs in sysroot. Does it exist?")
            else:
                libs = os.pathsep.join(libs)
                extra_envs.append(('LIBRARY_PATH', ':=', libs))

            if not os.path.isdir(inc):
                logger.warning("No include/ in sysroot. Does it exist?")
            else:
                extra_envs.append(('CPATH', ':=', inc))

        utils.install_script('pywrapper.py.tmpl', context.cross_env_exe, locals())

        for exe in ('python', 'python3'):
            exe = os.path.join(context.cross_bin_path, exe)
            if not os.path.exists(exe):
                utils.symlink(context.python_exe, exe)

        macosx_deployment_target = self.macosx_deployment_target
        # Install patches to environment
        utils.install_script('site.py.tmpl',
                os.path.join(context.lib_path, 'site.py'),
                locals())
        self.copy_and_patch_sysconfigdata(context)

        # cross-python is ready. We will use build-pip to install cross-pip
        # because 'python -m ensurepip' is likely to get confused and think
        # that there's nothing to do.
        if self.with_cross_pip:
            logger.info("Installing cross-pip")

            # Make sure we install the same version of pip and setuptools to
            logger.debug("Installing: %s", context.build_pip_reqs)
            subprocess.check_output([context.cross_env_exe, '-m', 'pip',
                '--disable-pip-version-check',
                'install',
                '--ignore-installed',
                '--prefix='+context.cross_env_dir] + context.build_pip_reqs)


    def copy_and_patch_sysconfigdata(self, context):
        """
        Put sysconfigdata file in the crossenv/lib directory. We will
        transform CC, CXX, and related variables as requested.
        """

        sysconfig_name = os.path.basename(self.host_sysconfigdata_file)
        # we always write a .py, but we might be reading from a .pyc
        # (i.e., from buildroot).
        sysconfig_name = os.path.splitext(sysconfig_name)[0] + '.py'
        cross_sysconfig = os.path.join(context.lib_path, sysconfig_name)

        # Patch all instances of CC, etc. We'll do a global search and
        # replace
        host_cc = self.real_host_cc[0]
        host_cxx = self.real_host_cxx[0]
        host_ar = self.real_host_ar[0]
        repl_cc = self.host_cc[0]
        repl_cxx = self.host_cxx[0]
        repl_ar = self.host_ar[0]
        find_cc = re.compile(r'(?:^|(?<=\s))%s(?=\s|$)' % re.escape(host_cc))
        find_cxx = re.compile(r'(?:^|(?<=\s))%s(?=\s|$)' % re.escape(host_cxx))
        find_ar = re.compile(r'(?:^|(?<=\s))%s(?=\s|$)' % re.escape(host_ar))

        cross_sysconfig_data = {}
        for key, value in self.host_sysconfigdata.__dict__.items():
            if key.startswith('__'):
                continue # misc module stuff like __name__, __builtins__
            cross_sysconfig_data[key] = value

        build_time_vars = {}
        for key, value in cross_sysconfig_data['build_time_vars'].items():
            if isinstance(value, str):
                value = find_ar.sub(repl_ar, value)
                value = find_cxx.sub(repl_cxx, value)
                value = find_cc.sub(repl_cc, value)

            build_time_vars[key] = value

        # Overrides from --config_var options
        for key, value in self.host_config_vars.items():
            build_time_vars[key] = value

        cross_sysconfig_data['build_time_vars'] = build_time_vars

        with open(cross_sysconfig, 'w') as fp:
            fp.write("# generated from %s\n" % self.host_sysconfigdata_file)
            for key, value in cross_sysconfig_data.items():
                fp.write("%s = " % key)
                pprint.pprint(value, stream=fp, compact=True)

    def post_setup(self, context):
        """
        Extra processing. Put scripts/binaries in the right place.
        """

        utils.install_script('cross-expose.py.tmpl',
                os.path.join(context.bin_path, 'cross-expose'),
                locals())

        # Don't trust these to be symlinks. A symlink to Python will mess up
        # the virtualenv.

        # Add cross-python alias to the path. This is just for
        # convenience and clarity.
        for exe in os.listdir(context.cross_bin_path):
            target = os.path.join(context.cross_bin_path, exe)
            if not os.path.isfile(target) or not os.access(target, os.X_OK):
                continue
            dest = os.path.join(context.bin_path, 'cross-' + exe)
            utils.make_launcher(target, dest)

        # Add build-python and build-pip to the path.
        for exe in os.listdir(context.build_bin_path):
            target = os.path.join(context.build_bin_path, exe)
            if not os.path.isfile(target) or not os.access(target, os.X_OK):
                continue
            dest = os.path.join(context.bin_path, 'build-' + exe)
            utils.make_launcher(target, dest)

        logger.info("Finishing up...")
        activate = os.path.join(context.bin_path, 'activate')
        with open(activate, 'w') as fp:
            fp.write(dedent(F('''\
                . %(context.cross_activate)s
                export PATH=%(context.bin_path)s:$PATH
                ''', locals())))

def parse_env_vars(env_vars):
    """Convert string descriptions of environment variable assignment into
    something that CrossEnvBuilder understands.

    :param env_vars:    An iterable of strings in the form 'FOO=BAR' or
                        'FOO?=BAR'
    :returns:           A list of (name, op, value)
    """

    parsed = []
    for spec in env_vars:
        spec = spec.lstrip()
        assign = '='
        try:
            name, value = spec.split('=',1)
        except IndexError:
            raise ValueError("Invalid variable %r. Must be in the form "
                              "NAME=VALUE" % spec)

        if name[-1:] in '?+:':
            assign = name[-1] + '='
            name = name[:-1]

        if not name.isidentifier():
            raise ValueError("Invalid variable name %r" % name)

        parsed.append((name, assign, value))
    return parsed


def parse_config_vars(config_vars):
    """Convert string descriptions of config variable assignment into
    something that CrossEnvBuilder understands.

    :param config_vars:  An iterable of strings in the form 'FOO=BAR'
    :returns:            A dictionary of name:value pairs.
    """

    result = {}
    for val in config_vars:
        try:
            name, value = val.split('=', 1)
        except ValueError:
            raise ValueError("--config-var must be of the form FOO=BAR")

        result[name] = value
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="""
                Create virtual Python environments for cross compiling
                """)

    parser.add_argument('--cross-prefix', action='store',
        help="""Specify the directory where cross-python files will be stored.
                By default, this is within <ENV_DIR>/cross. You can override
                this to have host packages installed in an existing sysroot,
                for example. Watch out though: this will write to bin.""")
    parser.add_argument('--system-site-packages', action='store_true',
        help="""Give the *build* python environment access to the system
                site-packages dir.""")
    parser.add_argument('--clear', action='store_const', const='default',
        help="""Delete the contents of the environment directory if it already
                exists. This clears build-python, but cross-python will be
                cleared only if --cross-prefix was not set. See also
                --clear-both, --clear-cross, and --clear-build.""")
    parser.add_argument('--clear-cross', action='store_const', const='cross',
        dest='clear',
        help="""This clears cross-python only. See also --clear, --clear-both,
                and --clear-build.""")
    parser.add_argument('--clear-build', action='store_const', const='build',
        dest='clear',
        help="""This clears build-python only. See also --clear, --clear-both,
                and --clear-cross.""")
    parser.add_argument('--clear-both', action='store_const', const='both',
        dest='clear',
        help="""This clears both cross-python and build-python. See also
                --clear, --clear-both, and --clear-cross.""")
    parser.add_argument('--without-pip', action='store_true',
        help="""Skips installing or upgrading pip in both the build and cross
                virtual environments. (Pip is bootstrapped by default.)""")
    parser.add_argument('--without-cross-pip', action='store_true',
        help="""Skips installing or upgrading pip in the cross virtual
                environment. Note that you cannot have cross-pip without
                build-pip.""")
    parser.add_argument('--relative-toolchain', action='store_true',
        help="""If the C/C++ compiler, etc. are stored with absolute paths,
                make them relative. Useful for when host-python was build with
                absolute paths in, e.g., a Docker image. The tools must be
                in $PATH for this to work.""")
    parser.add_argument('--cc', action='store',
        help="""Override the C compiler from what host-python was built
                with.""")
    parser.add_argument('--cxx', action='store',
        help="""Override the C++ compiler from what host-python was built
                with.""")
    parser.add_argument('--ar', action='store',
        help="""Override ar (static archive) from what host-python was built
                with.""")
    parser.add_argument('--config-var', action='append', default=[],
        help="""Override a specific config-time variable for host-python, such
                as CC, CCSHARED, etc. Usage: --config-var=FOO=BAR. All values
                are strings.""")
    parser.add_argument('--env', action='append', default=[],
        help="""An environment variable that will be added to the environment
                just before executing the python build executable. May be given
                multiple times. May be one of the following forms:

                'FOO=BAR' to unconditionally set the value.

                'FOO+=BAR' to append a value.

                'FOO?=BAR' to set a value only if not already set

                'FOO:=BAR' to append to a PATH-like variable, with colons
                between each element.""")
    parser.add_argument('--sysroot', action='store',
        help="""Explicitly set the sysroot for the cross-complier toolchain.
                If not given, an attempt will be made to guess. This is used
                to trick some packages into finding required headers and is
                optional.""")
    parser.add_argument('--sysconfigdata-file', action='store',
        help="""Explicitly set the sysconfigdata file path.
                If not given, all sysconfigdata files will be searched and
                will error if there are multiple files that have different
                values. This option is a workaround for specifically
                conda python where multiple sysconfigdata files exist.""")
    parser.add_argument('-v', '--verbose', action='count', default=0,
        help="""Verbose mode. May be specified multiple times to increase
                verbosity.""")
    parser.add_argument('--version', action='version',
        version='crossenv %s' % __version__)
    parser.add_argument('HOST_PYTHON',
        help="""The host Python to use. This should be the path to the Python
                executable, which may be in the source directory or an installed
                directory structure.""")
    parser.add_argument('ENV_DIR', nargs='+',
        help="""A directory to create the environment in.""")

    args = parser.parse_args()

    if args.verbose == 1:
        level = logging.INFO
    elif args.verbose > 1:
        level = logging.DEBUG
    else:
        level = logging.WARNING
    logging.basicConfig(level=level, format='%(levelname)s: %(message)s')

    try:
        if args.without_pip:
            args.without_cross_pip = True
        env = parse_env_vars(args.env)
        config_vars = parse_config_vars(args.config_var)

        builder = CrossEnvBuilder(host_python=args.HOST_PYTHON,
                cross_prefix=args.cross_prefix,
                build_system_site_packages=args.system_site_packages,
                clear=args.clear,
                extra_env_vars=env,
                with_cross_pip=not args.without_cross_pip,
                with_build_pip=not args.without_pip,
                host_sysroot=args.sysroot,
                host_cc=args.cc,
                host_cxx=args.cxx,
                host_ar=args.ar,
                host_relativize=args.relative_toolchain,
                host_config_vars = config_vars,
                host_sysconfigdata_file=args.sysconfigdata_file,
                )
        for env_dir in args.ENV_DIR:
            builder.create(env_dir)
    except Exception as e:
        logger.error('%s', e)
        logger.debug('Traceback:', exc_info=True)
        sys.exit(1)
