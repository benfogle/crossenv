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

import pkg_resources

from .utils import F
from . import utils

logger = logging.getLogger(__name__)

class CrossEnvBuilder(venv.EnvBuilder):

    def __init__(self, *,
            host_python,
            extra_env_vars=(),
            build_system_site_packages=False,
            clear=False,
            prompt=None,
            host_prefix=None,
            with_pip_host=False,
            with_pip_build=False):
        self.find_host_python(host_python)
        self.find_compiler_info()
        self.build_system_site_packages = build_system_site_packages
        self.extra_env_vars = extra_env_vars
        self.clear_build = clear in ('default', 'build', 'both')
        self.with_pip_host = with_pip_host
        self.with_pip_build = with_pip_build
        if host_prefix:
            self.host_prefix = os.path.abspath(host_prefix)
            self.clear_host = clear in ('host', 'both')
        else:
            self.host_prefix = None
            self.clear_host = clear in ('default', 'host', 'both')

        super().__init__(
                system_site_packages=False,
                clear=False,
                symlinks=True,
                upgrade=False,
                with_pip=False,
                prompt=prompt)

    def find_host_python(self, host):
        """Find Python paths and other info based on a path.
        The path may be a path to a binary, or a directory like you'd see in
        sys.prefix
        """

        host = os.path.abspath(host)
        if not os.path.exists(host):
            raise FileNotFoundError(f"{host} does not exist")
        elif not os.path.isfile(host):
            raise ValueError(f"Expected a path to a Python executable. "
                             f"Got {host}")
        else:
            self.host_project_base = os.path.dirname(host)

        if sysconfig._is_python_source_dir(self.host_project_base):
            self.host_makefile = os.path.join(self.host_project_base, 'Makefile')
            pybuilddir = os.path.join(self.host_project_base, 'pybuilddir.txt')
            try:
                with open(pybuilddir, 'r') as fp:
                    build_dir = fp.read().strip()
            except IOError:
                raise IOError(f"Cannot read {pybuilddir}: "
                              f"Build the host Python first!") from None

            self.host_home = self.host_project_base
            sysconfigdata = glob.glob(
                os.path.join(self.host_project_base,
                             build_dir,
                             '_sysconfigdata*.py'))
        else:
            # Assume host_project_base == {prefix}/bin and that this Python
            # mirrors the host Python's install paths.
            self.host_home = os.path.dirname(self.host_project_base)
            python_ver = 'python' + sysconfig.get_config_var('py_version_short')
            libdir = os.path.join(self.host_home, 'lib', python_ver)
            sysconfigdata = glob.glob(os.path.join(libdir, '_sysconfigdata*.py'))
            if not sysconfigdata:
                # Ubuntu puts it in a subdir plat-...
                sysconfigdata = glob.glob(
                        os.path.join(libdir, '*', '_sysconfigdata*.py'))

            makefile = glob.glob(os.path.join(libdir, '*', 'Makefile'))
            if not makefile:
                self.host_makefile = '' # fail later
            else:
                self.host_makefile = makefile[0]

        if not sysconfigdata:
            raise FileNotFoundError("No _sysconfigdata*.py found in host lib")
        elif len(sysconfigdata) > 1:
            raise ValueError("Malformed Python installation.")

        # We need paths to sysconfig data, and we need to import it to ask
        # a few questions.
        self.host_sysconfigdata_file = sysconfigdata[0]
        name = os.path.basename(sysconfigdata[0])
        self.host_sysconfigdata_name, _ = os.path.splitext(name)
        spec = importlib.util.spec_from_file_location(
                self.host_sysconfigdata_name,
                self.host_sysconfigdata_file)
        syscfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(syscfg)
        self.host_sysconfigdata = syscfg

        self.host_cc = syscfg.build_time_vars['CC']

        # Ask the makefile a few questions too
        if not os.path.exists(self.host_makefile):
            raise FileNotFoundError("Cannot find Makefile")

        self.host_platform = sys.platform # Default: not actually cross compiling
        with open(self.host_makefile, 'r') as fp:
            for line in fp:
                line = line.strip()
                if line.startswith('_PYTHON_HOST_PLATFORM='):
                    self.host_platform = line.split('=',1)[-1]
                    break

    def find_compiler_info(self):
        def run_compiler(arg):
            cmdline = [self.host_cc, arg]
            try:
                return subprocess.check_output(cmdline, universal_newlines=True)
            except CalledProcessError:
                return None

        self.host_sysroot = None

        # TODO: Clang
        if run_compiler('--version') is None:
            raise RuntimeError(
                "Cannot run cross-compiler! Extension modules won't build!")
            return

        self.host_sysroot = run_compiler('-print-sysroot').strip()

    def create(self, env_dir):
        env_dir = os.path.abspath(env_dir)
        context = self.ensure_directories(env_dir)
        self.make_build_python(context)
        self.make_host_python(context)
        self.post_setup(context)

    def ensure_directories(self, env_dir):
        # Directory structure:
        #
        # ENV_DIR/
        #   host/       host-python venv. Empty bin/
        #   build/      build-python venv. All scripts, etc. here.
        #   lib/        cross libs for setting up host-python
        #   bin/        holds activate scripts.

        if os.path.exists(env_dir) and (self.clear_host or self.clear_build):
            subdirs = os.listdir(env_dir)
            for sub in subdirs:
                if sub in ('host', 'build'):
                    continue
                utils.remove_path(os.path.join(env_dir, sub))

        context = super().ensure_directories(env_dir)
        context.lib_path = os.path.join(env_dir, 'lib')
        utils.mkdir_if_needed(context.lib_path)
        return context

    def make_build_python(self, context):
        context.build_env_dir = os.path.join(context.env_dir, 'build')
        logger.info("Creating build-python environment")
        env = venv.EnvBuilder(
                system_site_packages=self.build_system_site_packages,
                clear=self.clear_build,
                with_pip=self.with_pip_build)
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

    def make_host_python(self, context):
        logger.info("Creating host-python environment")
        if self.host_prefix:
            context.host_env_dir = self.host_prefix
        else:
            context.host_env_dir = os.path.join(context.env_dir, 'host')
        clear_host = self.clear in ('default', 'host-only', 'both')
        env = venv.EnvBuilder(
                system_site_packages=False,
                clear=self.clear_host,
                symlinks=True,
                upgrade=False,
                with_pip=False)
        env.create(context.host_env_dir)
        context.host_bin_path = os.path.join(context.host_env_dir, 'bin')
        context.host_env_exe = os.path.join(
                context.host_bin_path, context.python_exe)
        context.host_cfg_path = os.path.join(context.host_env_dir, 'pyvenv.cfg')
        context.host_activate = os.path.join(context.host_bin_path, 'activate')

        # Remove binaries. We'll run from elsewhere
        for exe in os.listdir(context.host_bin_path):
            if not exe.startswith('activate'):
                utils.remove_path(os.path.join(context.host_bin_path, exe))

        # Alter pyvenv.cfg
        with utils.overwrite_file(context.host_cfg_path) as out:
            with open(context.host_cfg_path) as inp:
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

        # If this venv is generated from a host-python still in its
        # build directory, rather than installed, then our modifications
        # prevent build-python from finding its pure-Python libs, which
        # will cause a crash on startup. Add them back to PYTHONPATH.
        # Also: 'stdlib' might not be acurate if build-python is in a build
        # directory.
        stdlib = os.path.abspath(os.path.dirname(os.__file__))

        with open(context.host_env_exe, 'w') as fp:
            fp.write(dedent('''\
                #!/bin/sh
                _base=${0##*/}
                export PYTHON_CROSSENV=1
                '''))
            fp.write(dedent(F('''\
                export _PYTHON_PROJECT_BASE="%(self.host_project_base)s"
                export _PYTHON_HOST_PLATFORM="%(self.host_platform)s"
                export _PYTHON_SYSCONFIGDATA_NAME="%(sysconfig_name)s"
                export PYTHONHOME="%(self.host_home)s"
                export PYTHONPATH="%(context.lib_path)s:%(stdlib)s${PYTHONPATH:+:$PYTHONPATH}"
                ''', locals())))

            # Add sysroot to various environment variables. This doesn't help
            # compiling, but some packages try to do manual checks for existance
            # of headers and libraries. This will help them find things.
            if self.host_sysroot:
                libs = os.path.join(self.host_sysroot, 'usr', 'lib*')
                libs = glob.glob(libs)
                if not libs:
                    logger.warning("No libs in sysroot. Does it exist?")
                else:
                    libs = os.pathsep.join(libs)
                    fp.write(F('export LIBRARY_PATH=%(libs)s\n', locals()))

                inc = os.path.join(self.host_sysroot, 'usr', 'include')
                if not os.path.isdir(inc):
                    logger.warning("No include/ in sysroot. Does it exist?")
                else:
                    fp.write(F('export CPATH=%(inc)s\n', locals()))

            for name, assign, val in self.extra_env_vars:
                if assign == '=':
                    fp.write(F('export %(name)s=%(val)s\n', locals()))
                elif assign == '?=':
                    fp.write(F('[ -z "${%(name)s}" ] && export %(name)s=%(val)s\n',
                        locals()))
                else:
                    assert False, "Bad assignment value %r" % assign

            # We want to alter argv[0] so that sys.executable will be correct.
            # We can't do this in a POSIX-compliant way, so we'll break
            # into Python
            fp.write(dedent(F('''\
                exec %(context.build_env_exe)s -c '
                import sys
                import os
                os.execv("%(context.build_env_exe)s", sys.argv[1:])
                ' "%(context.host_bin_path)s/$_base" "$@"
                ''', locals())))
        os.chmod(context.host_env_exe, 0o755)
        for exe in ('python', 'python3'):
            exe = os.path.join(context.host_bin_path, exe)
            if not os.path.exists(exe):
                utils.symlink(context.python_exe, exe)

        # Modifiy site.py
        script = os.path.join('scripts', 'site.py')
        src = pkg_resources.resource_string(__name__, script).decode()

        build_path = context.build_sys_path
        src = F(src, locals())
        dst_name = os.path.join(context.lib_path, 'site.py')
        with open(dst_name, 'w') as fp:
            fp.write(src)

        # Copy sysconfigdata
        shutil.copy(self.host_sysconfigdata_file, context.lib_path)
       
        # host-python is ready.
        if self.with_pip_host:
            logger.info("Installing host-pip")
            subprocess.check_call([context.host_env_exe, '-m', 'ensurepip',
                '--default-pip', '--upgrade'])

        # Add host-python alias to the path. This is just for
        # convenience and clarity.
        for exe in os.listdir(context.host_bin_path):
            target = os.path.join(context.host_bin_path, exe)
            if not os.path.isfile(target) or not os.access(target, os.X_OK):
                continue
            dest = os.path.join(context.bin_path, 'host-' + exe)
            utils.symlink(target, dest)

        # Add build-python and build-pip to the path.
        for exe in os.listdir(context.build_bin_path):
            target = os.path.join(context.build_bin_path, exe)
            if not os.path.isfile(target) or not os.access(target, os.X_OK):
                continue
            dest = os.path.join(context.bin_path, 'build-' + exe)
            utils.symlink(target, dest)



    def post_setup(self, context):
        logger.info("Finishing up...")
        activate = os.path.join(context.bin_path, 'activate')
        with open(activate, 'w') as fp:
            fp.write(dedent(F('''\
                . %(context.host_activate)s
                export PATH=%(context.bin_path)s:$PATH
                ''', locals())))

def parse_env_vars(env_vars):
    parsed = []
    for spec in env_vars:
        spec = spec.lstrip()
        assign = '='
        try:
            name, value = spec.split('=',1)
        except IndexError:
            raise ValueError(f"Invalid variable {spec!r}. Must be in the form "
                              "NAME=VALUE or NAME?=VALUE")
        if name.endswith('?'):
            assign = '?='
            name = name[:-1]

        if not name.isidentifier():
            raise ValueError(f"Invalid variable name {name!r}")

        parsed.append((name, assign, value))
    return parsed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="""
                Create virtual Python environments for cross compiling
                """)

    parser.add_argument('--host-prefix', action='store',
        help="""Specify the directory where host-python files will be stored.
                By default, this is within <ENV_DIR>/host. You can override
                this to have host packages installed in an existing sysroot,
                for example.""")
    parser.add_argument('--system-site-packages', action='store_true',
        help="""Give the *build* python environment access to the system
                site-packages dir.""")
    parser.add_argument('--clear', action='store_const', const='default',
        help="""Delete the contents of the environment directory if it already
                exists. This clears build-python, but host-python will be
                cleared only if --host-prefix was not set. See also
                --clear-both, --clear-host, and --clear-build.""")
    parser.add_argument('--clear-host', action='store_const', const='host',
        dest='clear',
        help="""This clears host-python only. See also --clear, --clear-both,
                and --clear-build.""")
    parser.add_argument('--clear-build', action='store_const', const='build',
        dest='clear',
        help="""This clears build-python only. See also --clear, --clear-both,
                and --clear-host.""")
    parser.add_argument('--clear-both', action='store_const', const='both',
        dest='clear',
        help="""This clears both host-python and build-python. See also
                --clear, --clear-both, and --clear-host.""")
    parser.add_argument('--without-pip', action='store_true',
        help="""Skips installing or upgrading pip in both the build and host
                virtual environments. (Pip is bootstrapped by default.)""")
    parser.add_argument('--without-pip-build', action='store_true',
        help="""Skips installing or upgrading pip the build virtual
                environments.""")
    parser.add_argument('--without-pip-host', action='store_true',
        help="""Skips installing or upgrading pip in the host virtual
                environment.""")
    parser.add_argument('--prompt', action='store',
        help="""Provides an alternative prompt prefix for this environment.""")
    parser.add_argument('--env', action='append', default=[],
        help="""An environment variable in the form FOO=BAR that will be
                added to the environment just before executing the python
                build executable. May be given multiple times. The form
                FOO?=BAR is also allowed to assign FOO only if not already
                set.""")
    parser.add_argument('-v', '--verbose', action='count', default=0,
        help="""Verbose mode. May be specified multiple times to increase
                verbosity.""")
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
            args.without_pip_host = True
            args.without_pip_build = True
        env = parse_env_vars(args.env)

        builder = CrossEnvBuilder(host_python=args.HOST_PYTHON,
                build_system_site_packages=args.system_site_packages,
                clear=args.clear,
                prompt=args.prompt,
                extra_env_vars=env,
                with_pip_host=not args.without_pip_host,
                with_pip_build=not args.without_pip_build,
                )
        for env_dir in args.ENV_DIR:
            builder.create(env_dir)
    except Exception as e:
        logger.error('%s', e)
        logger.debug('Traceback:', exc_info=True)
