##########################
# Basic download/compile
#########################

from textwrap import dedent
import os
import copy
import zipfile

from .testutils import make_crossenv


def test_build_simple(tmp_path, host_python, build_python, get_resource):
    # It's a huge PITA to do out-of-source with setuptools, so we'll just
    # make a copy.
    source = get_resource('hello-module:source')
    build = source.make_copy()

    # Take care to prevent creation of a .pth file; we don't want to have to mess
    # with sitecustomize.py stuff to make this work.
    crossenv = make_crossenv(tmp_path, host_python, build_python)
    crossenv.check_call(['python', 'setup.py', 'install',
        '--single-version-externally-managed',
        '--root', build.path,
        '--install-lib', '.'], cwd=build.path)

    host_python.setenv('PYTHONPATH', str(build.path) + ':$PYTHONPATH')
    host_python.check_call([host_python.binary, '-c', dedent('''\
            import hello
            assert hello.hello() == 'Hello, world'
            ''')])

def test_wheel_simple(tmp_path, host_python, build_python, get_resource):
    source = get_resource('hello-module:source')
    build = source.make_copy()

    crossenv = make_crossenv(tmp_path, host_python, build_python)
    crossenv.check_call(['pip', 'install', 'wheel'])
    crossenv.check_call(['python', 'setup.py', 'bdist_wheel'], cwd=build.path)

    mods = build.path / 'mods'
    for whl in build.path.glob('dist/*.whl'):
        with zipfile.ZipFile(whl) as zp:
            zp.extractall(mods)

    host_python.setenv('PYTHONPATH', str(mods) + ':$PYTHONPATH')
    host_python.check_call([host_python.binary, '-c', dedent('''\
            import hello
            assert hello.hello() == 'Hello, world'
            ''')])

def test_pip_install_numpy(tmp_path, host_python, build_python):
    crossenv = make_crossenv(tmp_path, host_python, build_python)
    crossenv.check_call(['cross-pip', '--no-cache-dir', 'install',
        'numpy==1.18.1', 'pytest==5.3.5'])

    # Run some tests under emulation. We don't do the full numpy test suite
    # because 1) it's very slow, and 2) there are some failing tests.
    # The failing tests might be an issue with numpy on the given archtecture,
    # or with qemu, or who knows, but in any case, it's really beyond the scope
    # of this project to address. We'll choose a quick, but nontrivial set of
    # tests to run.

    host_python.setenv('PYTHONPATH',
            str(crossenv.cross_site_packages) + ':$PYTHONPATH')
    host_python.check_call([host_python.binary, '-c', dedent('''\
            import sys, numpy
            ok = numpy.test(tests=['numpy.polynomial'])
            sys.exit(ok != True)
            ''')])

def test_pip_install_bcrypt(tmp_path, host_python, build_python):
    crossenv = make_crossenv(tmp_path, host_python, build_python)
    crossenv.check_call(['build-pip', '--no-cache-dir', 'install', 'cffi'])
    crossenv.check_call(['cross-pip', '--no-cache-dir', 'install', 'bcrypt'])

    # From the bcrypt test suites
    host_python.setenv('PYTHONPATH',
            str(crossenv.cross_site_packages) + ':$PYTHONPATH')
    output = host_python.check_output([host_python.binary, '-c', dedent('''
            import bcrypt, sys
            pw = b"Kk4DQuMMfZL9o"
            salt = b"$2b$04$cVWp4XaNU8a4v1uMRum2SO"
            print(bcrypt.hashpw(pw, salt).decode('ascii'))
            ''')])
    output = output.strip()
    expected = b"$2b$04$cVWp4XaNU8a4v1uMRum2SO026BWLIoQMD/TXg5uZV.0P.uO8m3YEm"
    assert output == expected
