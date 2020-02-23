#######################################################################
# These are tests to make sure that our prebuilt files are working
# correctly.
#######################################################################
from textwrap import dedent
import os
import subprocess

import pytest

def test_build_python_runs(build_python):
    build_python.check_call([build_python.binary, '--version'])

def test_host_python_emulates(host_python):
    host_python.check_call([host_python.binary, '--version'])

def test_cross_compiler_runs(build_python, host_python):
    cc = host_python.check_output([host_python.binary, '-c', dedent('''\
            import sysconfig
            print(sysconfig.get_config_var("CC"))
            ''')],
            universal_newlines=True)

    # Build-python should come with the correct path to the cross compiler
    # could be a whole shell command in there, so run with shell=True
    cmdline = cc.strip() + ' --version'
    build_python.check_call(cmdline, shell=True)
