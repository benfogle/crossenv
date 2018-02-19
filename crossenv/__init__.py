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


class CrossEnvBuilder(venv.EnvBuilder):
    def __init__(self, *, host_python, **kwargs):
        self.find_host_python(host_python)
        self.find_compiler_info()
        kwargs['symlinks'] = True
        kwargs['with_pip'] = True
        super().__init__(**kwargs)

    def find_host_python(self, host):
        """Find Python paths and other info based on a path.
        The path may be a path to a binary, or a directory like you'd see in
        sys.prefix
        """

        host = os.path.abspath(host)
        if os.path.isfile(host):
            self.host_project_base = os.path.dirname(host)
        elif os.path.isdir(host):
            self.host_project_base = host
        else:
            raise FileNotFoundError(f"No such file or directory {host}")

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
                os.path.join(pybuilddir, '_sysconfigdata*.py'))
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
        self.host_sysconfigdata = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.host_sysconfigdata)
        self.host_cc = self.host_sysconfigdata.build_time_vars['CC']

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
        env = venv.EnvBuilder(system_site_packages=True,
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

        # Add build-python and build-pip to the path. These need to be
        # scripts. If we just symlink/hardlink, we'll grab the wrong env.
        def link_script(name):
            target = os.path.join(context.build_bin_path, name)
            path = os.path.join(context.bin_path, 'build-' + name)
            with open(path, 'w') as fp:
                fp.write(dedent(f'''\
                    #!/bin/sh
                    exec {target} "$@"
                    '''))
            os.chmod(path, 0o755)

        link_script('python')
        link_script('pip')

    def post_setup(self, context):
        # Replace python binary with a script that sets the environment
        # variables. Don't do this in bin/activate, because it's a pain
        # to set/unset properly (and for csh, fish as well).
        exe_dir, exe = os.path.split(context.env_exe)
        context.real_env_exe = os.path.join(exe_dir, '_'+exe)
        shutil.move(context.env_exe, context.real_env_exe)
        sysconfig_name = os.path.basename(self.host_sysconfigdata_file)
        sysconfig_name, _ = os.path.splitext(sysconfig_name)

        with open(context.env_exe, 'w') as fp:
            fp.write(dedent(f'''\
                #!/bin/sh
                export _PYTHON_PROJECT_BASE={self.host_project_base}
                export _PYTHON_HOST_PLATFORM={self.host_platform}
                export PYTHONPATH=$VIRTUAL_ENV/lib/cross:$PYTHONPATH
                export _PYTHON_SYSCONFIGDATA_NAME={sysconfig_name}
                export PYTHONHOME={self.host_home}
                '''))

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
                    fp.write(f'export LIBRARY_PATH={libs}\n')

                inc = os.path.join(self.host_sysroot, 'usr', 'include')
                if not os.path.isdir(inc):
                    logger.warning("No include/ in sysroot. Does it exist?")
                else:
                    fp.write(f'export CPATH={inc}\n')

            fp.write(f'exec {context.real_env_exe} "$@"\n')
        os.chmod(context.env_exe, 0o755)

        # Modifiy site.py
        script = os.path.join('scripts', 'site.py')
        src = pkg_resources.resource_string(__name__, script).decode()

        src = src.format(build_path=context.build_sys_path)
        dst_name = os.path.join(context.cross_lib, 'site.py')
        with open(dst_name, 'w') as fp:
            fp.write(src)

        # Copy sysconfigdata
        shutil.copy(self.host_sysconfigdata_file, context.cross_lib)
        

def main():
    host = sys.argv[1]
    dest = sys.argv[2]
    builder = CrossEnvBuilder(host_python=host)
    builder.create(dest)
