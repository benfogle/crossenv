########################################
# Test general usage
########################################

import subprocess
import pytest
from .testutils import make_crossenv


def test_no_pip(tmp_path, host_python, build_python):
    crossenv = make_crossenv(tmp_path, host_python, build_python,
            '--without-pip')

    # pip and pip3 could be in the user PATH, so call exactly the one we
    # expect
    pip_variants = [
        'pip',
        'pip3',
        'cross-pip',
        'cross-pip3',
        'build-pip',
        'build-pip3',
    ]

    bin_variants = [
        crossenv.bindir,
        crossenv.cross_bindir,
        crossenv.build_bindir,
    ]

    for bindir in bin_variants:
        for pip in pip_variants:
            pip = bindir / pip

            with pytest.raises(FileNotFoundError):
                crossenv.check_call([pip, '--version'])

    python_variants = [
        'python',
        'python3',
        'cross-python',
        'cross-python3',
        'build-python',
        'build-python3',
    ]

    for python in python_variants:
        result = crossenv.run(
                    [python, '-m', 'pip', '--version'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True)
        assert result.returncode != 0, \
                "'%s -m pip' shouldn't succeed" % python
        assert 'no module named pip' in result.stdout.lower()

def test_no_cross_pip(tmp_path, host_python, build_python):
    crossenv = make_crossenv(tmp_path, host_python, build_python,
            '--without-cross-pip')

    # pip and pip3 could be in the user PATH, so call exactly the one we
    # expect
    pip_variants = [
        'pip',
        'pip3',
        'cross-pip',
        'cross-pip3',
    ]

    bin_variants = [
        crossenv.bindir,
        crossenv.cross_bindir,
    ]

    for bindir in bin_variants:
        for pip in pip_variants:
            pip = bindir / pip

            with pytest.raises(FileNotFoundError):
                crossenv.check_call([pip, '--version'])

    # cross-python -m pip will still work, because cross-python
    # can import build-python's modules.

def test_cross_prefix(tmp_path, host_python, build_python):
    env = tmp_path / 'cross'
    prefix = tmp_path / 'this_is_a_test'

    crossenv = make_crossenv(env, host_python, build_python,
            '--without-pip', '--cross-prefix={}'.format(prefix))

    cross_python = prefix / 'bin' / 'python'
    assert cross_python.is_file()
    
    activate = env / 'bin' / 'activate'
    out = crossenv.check_output(
            ['bash', '-c', '. {}; echo $PS1'.format(activate)],
            universal_newlines=True)

    assert '(this_is_a_test)' in out
