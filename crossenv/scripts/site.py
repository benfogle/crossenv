import importlib
import importlib.util
import sys
import os
import sysconfig

def restore_site():
    """Restore the original site module"""

    cross_dir = os.path.dirname(__file__)
    new_path = [ p for p in sys.path
            if not os.path.exists(p) or not os.path.samefile(p, cross_dir) ]
    sys.path = new_path
    sys.path.extend({build_path})

    del sys.modules['site']
    import site
    sys.path.append(cross_dir)

def fixup_sys():
    # sysconfig should be correct, but some little parts of
    # sys are hardcoded (but changable)
    multiarch = sysconfig.get_config_var('MULTIARCH')
    if multiarch is None:
        try:
            del sys.implementation._multiarch
        except AttributeError:
            pass
    else:
        sys.implementation._multiarch = multiarch

fixup_sys()
restore_site()
