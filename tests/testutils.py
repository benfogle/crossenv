import os
import hashlib
import subprocess
import string
import fcntl
from contextlib import contextmanager

def hash_file(path):
    ctx = hashlib.sha256()
    with open(path, 'rb') as fp:
        data = fp.read(0x4000)
        while data:
            ctx.update(data)
            data = fp.read(0x4000)
    return ctx.hexdigest()


class ExecEnvironment:
    '''Mostly some wrappers around popen'''

    def __init__(self):
        # prepopulate the environment
        self.environ = {
            'PATH': os.environ.get('PATH', ''),
        }
        self.cwd = None

    def expand_environ(self, value):
        # os.path.expandvars exists, but doesn't operate on an arbitrary
        # environment. We might clobber changes to $PATH, etc. if we use
        # it.
        class EnvDict:
            '''trick Template.substitute into converting $NOTFOUND into '''
            def __init__(self, src):
                self.src = src
            def __getitem__(self, key):
                return self.src.get(key, '')

        if value is None:
            return value
        value = str(value)
        return string.Template(value).substitute(EnvDict(self.environ))

    def setenv(self, name, value):
        if value is None:
            self.environ.pop(name, None)
        else:
            value = self.expand_environ(value)
            self.environ[name] = value

    def _alter_env(self, updated, original):
        env = original.copy()

        # Calculate all new values without updating
        new_env = {}
        for name, value in updated.items():
            if value is not None:
                value = self.expand_environ(value)
            new_env[name] = value

        # Update new values, remove as necessary
        for name, value in new_env.items():
            if value is None and name in env:
                del env[name]
            else:
                env[name] = value
        return env

    def _popen(self, func, *args, **kwargs):
        if self.environ:
            env = kwargs.get('env', os.environ)
            env = self._alter_env(self.environ, env)
            kwargs['env'] = env
        if self.cwd and 'cwd' not in kwargs:
            kwargs['cwd'] = self.cwd

        return func(*args, **kwargs)


    def run(self, *args, **kwargs):
        return self._popen(subprocess.run, *args, **kwargs)


    def popen(self, *args, **kwargs):
        return self._popen(subprocess.Popen, *args, **kwargs)


    def check_call(self, *args, **kwargs):
        return self._popen(subprocess.check_call, *args, **kwargs)


    def check_output(self, *args, **kwargs):
        return self._popen(subprocess.check_output, *args, **kwargs)


class CrossenvEnvironment(ExecEnvironment):
    def __init__(self, build_python, crossenv_dir, creation_log=''):
        super().__init__()

        self.creation_log = creation_log
        self.environ = build_python.environ.copy()
        self.cwd = build_python.cwd

        self.crossenv_dir = crossenv_dir
        self.bindir = crossenv_dir / 'bin'

        site = sorted(crossenv_dir.glob('build/lib/python*/site-packages'))[0]
        self.build_bindir = crossenv_dir / 'build/bin'
        self.build_site_packages = site

        sites = crossenv_dir.glob('cross/lib/python*/site-packages')
        sites = sorted(sites)
        if sites:
            self.cross_site_packages = sites[0]
            self.cross_bindir = crossenv_dir / 'cross/bin'
        else:
            self.cross_site_packages = None
            self.cross_bindir = None

        # Mimic some of what crossenv_dir/bin/activate would do
        self.setenv('PATH', '{}:{}:$PATH'.format(self.bindir,
            self.cross_bindir))

def make_crossenv(crossenv_dir, host_python, build_python, *args, **kwargs):
    cmdline = [ build_python.binary, '-m', 'crossenv', host_python.binary,
            crossenv_dir ]
    cmdline.extend(args)
    result = build_python.run(cmdline,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, universal_newlines=True,
            **kwargs)
    if result.returncode:
        print(result.stdout) # capture output on error
        assert False, "Could not make crossenv!"
    return CrossenvEnvironment(build_python, crossenv_dir,
            creation_log=result.stdout)

@contextmanager
def open_lock_file(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o660)
    with open(fd, 'r+') as fp:
        fcntl.flock(fp, fcntl.LOCK_EX)
        try:
            data = fp.read(64)
            if data:
                try:
                    yield int(data)
                    return
                except ValueError:
                    fp.truncate(0)
            yield None
            fp.write(str(os.getpid()))
        finally:
            fp.flush()
            fcntl.flock(fp, fcntl.LOCK_UN)
