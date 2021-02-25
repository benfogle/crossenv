from textwrap import dedent

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
