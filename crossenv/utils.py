import contextlib
import tempfile
import shutil
import os
from textwrap import dedent
import pkgutil

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

def F(s, values):
    values = FormatMapping(values)
    return s % values


@contextlib.contextmanager
def overwrite_file(name, mode='w', perms=None):
    '''A context manager that will overwrite the given file
    only after it was closed with no error'''

    fp = tempfile.NamedTemporaryFile(mode, delete=False)
    try:
        yield fp
        fp.close()
        if perms is not None:
            os.chmod(fp.name, perms)
        shutil.move(fp.name, name)
    except Exception as e:
        fp.close()
        try:
            os.unlink(fp.name)
        except OSError:
            pass
        raise

def mkdir_if_needed(d):
    if not os.path.exists(d):
        os.makedirs(d)
    elif os.path.islink(d) or os.path.isfile(d):
        raise ValueError('Unable to make directory %r' % d)

def remove_path(p):
    if os.path.islink(p) or not os.path.isdir(p):
        os.unlink(p)
    else:
        shutil.rmtree(p)

def symlink(src, dst):
    if os.path.exists(dst):
        os.unlink(dst)
    os.symlink(src, dst)

def make_launcher(src, dst):
    with overwrite_file(dst, perms=0o755) as fp:
        fp.write(dedent(F('''\
            #!/bin/sh
            exec %(src)s "$@"
            ''', locals())))

def install_script(name, dst, values, perms=0o755):
    srcname = os.path.join('scripts', name)
    src = pkgutil.get_data(__package__, srcname)
    src = F(src.decode(), values)
    mkdir_if_needed(os.path.dirname(dst))

    with overwrite_file(dst, perms=perms) as fp:
        fp.write(src)
