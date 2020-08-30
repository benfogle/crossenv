########################################
# Test options that alter the compiler
########################################

from textwrap import dedent
import re

from .testutils import make_crossenv


def test_set_compiler(tmp_path, host_python, build_python, get_resource):
    crossenv = make_crossenv(tmp_path, host_python, build_python,
            '--cc=/bin/true')
    compiler = crossenv.check_output(['python', '-c', dedent('''\
        import sysconfig
        print(sysconfig.get_config_var("CC"))
        ''')])
    compiler = compiler.strip()
    assert compiler == b'/bin/true'

def test_wrong_architecture(tmp_path, host_python, build_python, get_resource):
    """Make sure we get a warning if the compiler doesn't seem right. Requires
    gcc."""

    crossenv = make_crossenv(tmp_path, host_python, build_python,
            '--cc=/usr/bin/gcc')
    for line in crossenv.creation_log.splitlines():
        if re.match(r'WARNING:.*architecture', line):
            return
    assert False, "Crossenv did not detect wrong architecture"
