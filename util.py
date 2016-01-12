import locale, os, subprocess

def read_every_line(stream):
    '''Workaround for Py2, which blocks when iterating over a file object.'''
    nl = None
    while True:
        l = stream.readline()
        if l:
            yield l
        if not nl:
            nl = b"\n" if isinstance(l, bytes) else "\n"
        if not l.endswith(nl):
            break

#@snip[
#@provides: PREFERREDENCODING
#@requires: mod:locale
PREFERREDENCODING = locale.getpreferredencoding()
#@]

#@snip[
#@provides: null_context_manager
class NullContextManager(object):

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

null_context_manager = NullContextManager()
#@]

#@snip[
#@provides: CompletedProcess Popen check_output run
#@requires: mod:os mod:subprocess null_context_manager
DEVNULL = -3

def run(*args, input=None, check=False, **kwargs):
    '''Mimics the API of 'run' in Python 3.5 but does not support 'timeout'.'''
    if input is not None:
        if "stdin" in kwargs:
            raise ValueError("stdin and input arguments may not both be used.")
        kwargs["stdin"] = subprocess.PIPE
    proc = Popen(*args, **kwargs)
    try:
        out, err = proc.communicate(input)
    except:
        proc.kill()
        proc.wait()
        raise
    result = CompletedProcess(proc.args, proc.returncode,
                              stdout=out, stderr=err)
    if check:
        result.check_returncode()
    return result

def check_output(*args, **kwargs):
    return run(*args, check=True, stdout=subprocess.PIPE, **kwargs).stdout

def Popen(args, stdin=None, stdout=None, stderr=None, **kwargs):
    '''A variant of Popen that accepts 'DEVNULL' for standard streams.'''
    devnull = None
    open_devnull = lambda: devnull or open(os.devnull, "r+b")
    if stdin == DEVNULL:
        devnull = open_devnull()
        stdin = devnull
    if stdout == DEVNULL:
        devnull = open_devnull()
        stdout = devnull
    if stderr == DEVNULL:
        devnull = open_devnull()
        stderr = devnull
    with devnull or NullContextManager():
        return subprocess.Popen(args, stdin=stdin, stdout=stdout,
                                stderr=stderr, **kwargs)

class CompletedProcess(object):

    def __init__(self, args, returncode, stdout=None, stderr=None):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def check_returncode(self):
        from subprocess import CalledProcessError
        if not self.returncode:
            return
        # older versions of Python did not support output and/or stderr arguments
        try:
            raise CalledProcessError(
                self.returncode,
                self.args,
                output=self.stdout,
                stderr=self.stderr,
            )
        except TypeError:
            pass
        try:
            raise CalledProcessError(
                self.returncode,
                self.args,
                output=self.stdout,
            )
        except TypeError:
            pass
        raise CalledProcessError(
            self.returncode,
            self.args,
        )

    def __repr__(self):
        s = "CompletedProcess(args=" + repr(self.args)
        s += ", returncode=" + repr(self.returncode)
        if self.stdout is not None:
            s += ", stdout=" + repr(self.stdout)
        if self.stderr is not None:
            s += ", stderr=" + repr(self.stderr)
        s += ")"
        return s
#@]
