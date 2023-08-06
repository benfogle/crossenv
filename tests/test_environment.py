import os
import re
from textwrap import dedent

from .testutils import make_crossenv

def test_uname(crossenv, architecture):
    # We don't test all of uname. We currently have no values for release or
    # version, and we don't really care about node.
    out = crossenv.check_output(['python', '-c', dedent('''\
            import os
            print(os.uname().sysname, os.uname().machine)
            ''')],
            universal_newlines=True)
    out = out.strip()
    expected = '{} {}'.format(architecture.system, architecture.machine)
    assert out == expected

def test_platform(crossenv, architecture):
    # Since uname isn't 100%, platform.platform() still looks a bit strange.
    # Test platform.uname() components
    #
    # Also: don't run 'python -m platform'. The way this works, a __main__
    # module is created and populated with code from the system library
    # platform module.  This __main__ module is completely separate from what
    # you get from 'import platform', so none of our patches apply to it!
    # There's no good way around that that I can think of.
    out = crossenv.check_output(['python', '-c', dedent('''\
            import platform
            print(platform.uname().system,
                  platform.uname().machine,
                  platform.uname().processor)
            ''')],
            universal_newlines=True)
    out = out.strip()
    expected = '{0} {1} {1}'.format(architecture.system, architecture.machine)
    assert out == expected

def test_sysconfig_platform(crossenv, architecture):
    out = crossenv.check_output(['python', '-c', dedent('''\
            import sysconfig
            print(sysconfig.get_platform())
            ''')],
            universal_newlines=True)
    out = out.strip()
    expected = '{}-{}'.format(architecture.system, architecture.machine)
    expected = expected.lower()
    assert out == expected

def test_no_manylinux(crossenv, architecture):
    crossenv.check_call(['pip', 'install', 'packaging'])
    out = crossenv.check_output(['python', '-c', dedent('''\
            from packaging.tags import compatible_tags
            platforms = set(tag.platform for tag in compatible_tags())
            print('\\n'.join(platforms))
            ''')],
            universal_newlines=True)
    out = out.strip()
    assert 'manylinux' not in out

def test_explicit_platform_tags(tmp_path, host_python, build_python, architecture):
    crossenv = make_crossenv(
        tmp_path,
        host_python,
        build_python,
        '--platform-tag=foobar1234',
        '--platform-tag=mytag',
        )

    crossenv.check_call(['pip', 'install', 'packaging'])
    out = crossenv.check_output(['python', '-c', dedent('''\
            from packaging.tags import compatible_tags
            platforms = set(tag.platform for tag in compatible_tags())
            print('\\n'.join(platforms))
            ''')],
            universal_newlines=True)
    out = out.strip()
    assert 'foobar1234' in out
    assert 'mytag' in out

def test_explicit_manylinux(tmp_path, host_python, build_python, architecture):
    # not defined for all architectures, so pass them
    if architecture.machine not in ('x86_64', 'aarch64'):
        return

    crossenv = make_crossenv(tmp_path, host_python, build_python,
            '--manylinux=manylinux2014')

    crossenv.check_call(['pip', 'install', 'packaging'])
    out = crossenv.check_output(['python', '-c', dedent('''\
            from packaging.tags import compatible_tags
            platforms = set(tag.platform for tag in compatible_tags())
            print('\\n'.join(platforms))
            ''')],
            universal_newlines=True)
    out = out.strip()
    assert 'manylinux2014' in out
    assert 'manylinux_2_17' in out

def test_very_long_paths(tmp_path_factory, host_python, build_python):
    tmp = tmp_path_factory.mktemp('A'*128)
    dirname = tmp / ('B'*128)
    os.mkdir(dirname)
    assert len(str(dirname)) >= 256
    crossenv = make_crossenv(dirname, host_python, build_python)
    crossenv.check_call(['python', '--version'])

def test_very_long_paths(tmp_path_factory, host_python, build_python):
    tmp = tmp_path_factory.mktemp('A'*128)
    dirname = tmp / ('B'*128)
    os.mkdir(dirname)
    assert len(str(dirname)) >= 256
    crossenv = make_crossenv(dirname, host_python, build_python)
    crossenv.check_call(['python', '--version'])

def test_environment_leak(crossenv):
    # a regression test that used to cause scary warnings during build
    # processes. Triggered with subprocess.Popen with explicit environ
    out = crossenv.check_output(['python', '-c', dedent('''\
            import subprocess
            import sys
            import os

            env = os.environ.copy()
            python = sys.executable
            result = subprocess.run([python, '-c', 'print("ok")'], env=env)
            sys.exit(result.returncode)
            ''')],
            universal_newlines=True)
    assert 'Crossenv has leaked' not in out

def test_run_sysconfig_module(crossenv):
    # a regression test that 'python -m sysconfig' works as well as 'import
    # sysconfig'
    out = crossenv.check_output(['python', '-m', 'sysconfig'],
            universal_newlines=True)
    
    m = re.search(r'^\s*DESTDIRS = "(.*)"$', out, re.M)
    assert m is not None
    destdirs_cmdline = m.group(1)

    out = crossenv.check_output(['python', '-c', dedent('''\
            import sysconfig
            print(sysconfig.get_config_var('DESTDIRS'))
            ''')],
            universal_newlines=True)
    out = out.strip()
    assert destdirs_cmdline == out

def test_cross_expose(crossenv):
    out = crossenv.check_output(['pip', 'freeze'])
    assert b'colorama' not in out

    crossenv.check_call(['build-pip', 'install', 'colorama'])
    out = crossenv.check_output(['pip', 'freeze'])
    assert b'colorama' not in out

    crossenv.check_call(['cross-expose', 'colorama'])
    out = crossenv.check_output(['pip', 'freeze'])
    assert b'colorama' in out

    out = crossenv.check_output(['cross-expose', '--list'])
    assert b'colorama' in out

    crossenv.check_call(['cross-expose', '-u', 'colorama'])
    out = crossenv.check_output(['pip', 'freeze'])
    assert b'colorama' not in out

    out = crossenv.check_output(['cross-expose', '--list'])
    assert b'colorama' not in out

def test_machine_override(tmp_path, host_python, build_python):
    crossenv = make_crossenv(tmp_path, host_python, build_python,
            '--machine=foobar')

    out = crossenv.check_output(['python', '-c', dedent('''\
            import os, platform
            print(os.uname().machine, platform.machine())
            ''')],
            universal_newlines=True)
    out = out.strip()
    assert out == 'foobar foobar'
