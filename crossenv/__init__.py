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

import pkg_resources

logger = logging.getLogger(__name__)

# We're using %-style formatting everywhere because it's more convenient for
# building Python and Bourne Shell source code. We'll build some helpers to
# make it just a bit more like f-strings.

class FormatMapping:
    '''Map strings such that %(foo.bar)s works in %-format strings'''
    def __init__(self, mapping):
        self.mapping = mapping

    def __getitem__(self, key):
        parts = key.split('.')
        obj = self.mapping[parts[0]]
        for p in parts[1:]:
            obj = getattr(obj, p)
        return obj

def _f(s, values):
    values = FormatMapping(values)
    return s % values

class CrossEnvBuilder(venv.EnvBuilder):
    def __init__(self, *,
            host_python,
            extra_env_vars=(),
            build_system_site_packages=False,
            clear=False,
            prompt=None):
        self.find_host_python(host_python)
        self.find_compiler_info()
        self.build_system_site_packages = build_system_site_packages
        self.extra_env_vars = extra_env_vars
        super().__init__(symlinks=True, with_pip=True, clear=clear,
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

    def ensure_directories(self, env_dir):
        context = super().ensure_directories(env_dir)

        # We'll need our own cross library to hold modifications
        def create_if_needed(d):
            if not os.path.exists(d):
                os.makedirs(d)
            elif os.path.islink(d) or os.path.isfile(d):
                raise ValueError('Unable to create directory %r' % d)

        context.cross_lib = os.path.join(env_dir, 'lib', 'cross')
        create_if_needed(context.cross_lib)

        return context

    def create_configuration(self, context):
        # Make sure that the 'home = ...' line points to the host Python, not
        # the build Python.
        python_dir = context.python_dir
        context.python_dir = self.host_project_base
        super().create_configuration(context)
        context.python_dir = python_dir

    def setup_python(self, context):
        super().setup_python(context)

        # We'll need a venv for the build python. This will
        # let us easily install setup_requires stuff.
        context.build_python_dir = os.path.join(context.env_dir, 'lib', 'build')
        env = venv.EnvBuilder(
                system_site_packages=self.build_system_site_packages,
                clear=True,
                with_pip=True)
        env.create(context.build_python_dir)
        context.build_bin_path = os.path.join(context.build_python_dir, 'bin')
        context.build_env_exe = os.path.join(context.build_bin_path, 'python')
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

    def post_setup(self, context):
        # Replace python binary with a script that sets the environment
        # variables. Don't do this in bin/activate, because it's a pain
        # to set/unset properly (and for csh, fish as well).
        exe_dir, exe = os.path.split(context.env_exe)
        context.real_env_exe = os.path.join(exe_dir, '_'+exe)
        shutil.move(context.env_exe, context.real_env_exe)
        sysconfig_name = os.path.basename(self.host_sysconfigdata_file)
        sysconfig_name, _ = os.path.splitext(sysconfig_name)

        # If this venv is generated from a host-python still in its
        # build directory, rather than installed, then our modifications
        # prevent build-python from finding its pure-Python libs, which
        # will cause a crash on startup. Add them back to PYTHONPATH.
        # Also: 'stdlib' might not be acurate if build-python is in a build
        # directory.
        stdlib = os.path.abspath(os.path.dirname(os.__file__))
        pypath = _f('$VIRTUAL_ENV/lib/cross:%(stdlib)s', locals())

        with open(context.env_exe, 'w') as fp:
            fp.write(dedent(_f('''\
                #!/bin/sh
                export PYTHON_CROSSENV=1
                export _PYTHON_PROJECT_BASE=%(self.host_project_base)s
                export _PYTHON_HOST_PLATFORM=%(self.host_platform)s
                export _PYTHON_SYSCONFIGDATA_NAME=%(sysconfig_name)s
                export PYTHONHOME=%(self.host_home)s
                export PYTHONPATH=%(pypath)s${PYTHONPATH:+:$PYTHONPATH}
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
                    fp.write(_f('export LIBRARY_PATH=%(libs)s\n', locals()))

                inc = os.path.join(self.host_sysroot, 'usr', 'include')
                if not os.path.isdir(inc):
                    logger.warning("No include/ in sysroot. Does it exist?")
                else:
                    fp.write(_f('export CPATH=%(inc)s\n', locals()))

            for name, assign, val in self.extra_env_vars:
                if assign == '=':
                    fp.write(_f('export %(name)s=%(val)s\n', locals()))
                elif assign == '?=':
                    fp.write(_f('[ -z "${%(name)s}" ] && export %(name)s=%(val)s\n',
                        locals()))
                else:
                    assert False, "Bad assignment value %r" % assign

            # We want to alter argv[0] so that sys.executable will be correct.
            # We can't do this in a POSIX-compliant way, so we'll break
            # into Python
            fp.write(dedent(_f('''\
                exec %(context.build_env_exe)s -c '
                import sys
                import os
                os.execv("%(context.real_env_exe)s", sys.argv[1:])
                ' "$0" "$@"
                ''', locals())))
        os.chmod(context.env_exe, 0o755)

        # Modifiy site.py
        script = os.path.join('scripts', 'site.py')
        src = pkg_resources.resource_string(__name__, script).decode()

        build_path = context.build_sys_path
        src = _f(src, locals())
        dst_name = os.path.join(context.cross_lib, 'site.py')
        with open(dst_name, 'w') as fp:
            fp.write(src)

        # Copy sysconfigdata
        shutil.copy(self.host_sysconfigdata_file, context.cross_lib)
        
        # Add host-python alias to the path. This is just for
        # convenience and clarity.
        for exe in os.listdir(context.bin_path):
            target = os.path.join(context.bin_path, exe)
            if not exe.startswith('host-') and os.access(target, os.X_OK):
                dst = os.path.join(context.bin_path, 'host-' + exe)
                os.symlink(exe, dst)

        # Add build-python and build-pip to the path. These need to be
        # scripts. If we just symlink/hardlink, we'll grab the wrong env.
        for exe in os.listdir(context.build_bin_path):
            target = os.path.join(context.build_bin_path, exe)
            if not os.path.isfile(target) or not os.access(target, os.X_OK):
                continue
            dest = os.path.join(context.bin_path, 'build-' + exe)
            with open(dest, 'w') as fp:
                fp.write(dedent(_f('''\
                    #!/bin/sh
                    exec %(target)s "$@"
                    ''', locals())))
            os.chmod(dest, 0o755)


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

    parser.add_argument('--system-site-packages', action='store_true',
        help="""Give the *build* python environment access to the system
                site-packages dir.""")
    parser.add_argument('--clear', action='store_true',
        help="""Delete the contents of the environment directoy if it already
                exists.""")
    parser.add_argument('--prompt', action='store',
        help="""Provides an alternative prompt prefix for this environment.""")
    parser.add_argument('--env', action='append', default=[],
        help="""An environment variable in the form FOO=BAR that will be
                added to the environment just before executing the python
                build executable. May be given multiple times. The form
                FOO?=BAR is also allowed to assign FOO only if not already
                set.""")
    parser.add_argument('HOST_PYTHON',
        help="""The host Python to use. This should be the path to the Python
                executable, which may be in the source directory or an installed
                directory structure.""")
    parser.add_argument('ENV_DIR', nargs='+',
        help="""A directory to create the environment in.""")

    args = parser.parse_args()
    env = parse_env_vars(args.env)
    builder = CrossEnvBuilder(host_python=args.HOST_PYTHON,
            build_system_site_packages=args.system_site_packages,
            clear=args.clear,
            prompt=args.prompt,
            extra_env_vars=env)
    for env_dir in args.ENV_DIR:
        builder.create(env_dir)
