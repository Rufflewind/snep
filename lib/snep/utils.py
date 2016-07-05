from __future__ import unicode_literals
import functools, json, os

#@imports[
import ctypes
import errno
import io
import os
import shutil
import tempfile
#@]

#@snips[
#@MappingProxyType[
try:
    from types import MappingProxyType
except ImportError:
    def MappingProxyType(mapping):
        return mapping
#@]

#@StringIO[
try:
    from io import StringIO
except AttributeError:
    from cStringIO import StringIO
#@]

#@reachable_set[
def reachable_set(initial, neighbors_func):
    '''(Iterable<Node>, (Node) -> Iterable<neighborNode>) -> reachableSet'''
    queue = set(initial)
    seen = set()
    reachable = set(queue)
    while queue:
        node = queue.pop()
        neighbors = neighbors_func(node)
        if not (isinstance(neighbors, frozenset) or
                isinstance(neighbors, set)):
            neighbors = frozenset(neighbors)
        queue.update(neighbors)
        reachable.update(neighbors)
    return reachable
#@]

#@load_file[
#@requires: mod:io
def load_file(filename, binary=False, encoding=None,
              errors=None, newline=None):
    '''Read the contents of a file.'''
    mode = "r" + ("b" if binary else "")
    with io.open(filename, mode, encoding=encoding,
                 errors=errors, newline=newline) as stream:
        return stream.read()
#@]

#@try_remove[
#@requires: mod:os
def try_remove(path):
    try:
        os.remove(path)
    except OSError:
        return False
    return True
#@]

#@wrapped_open[
#@requires: mod:io
def wrapped_open(open, mode="r", encoding=None,
                 errors=None, newline=None, **kwargs):
    '''Enhance an `open`-like function to accept some additional arguments for
    controlling the text processing.  This is mainly done for compatibility
    with Python 2, where these additional arguments are often not accepted.'''
    if "b" in mode:
        if encoding is not None:
            raise Exception("'encoding' argument not supported in binary mode")
        if errors is not None:
            raise Exception("'errors' argument not supported in binary mode")
        if newline is not None:
            raise Exception("'newline' argument not supported in binary mode")
        return open(mode=mode, **kwargs)
    else:
        mode = mode.replace("t", "") + "b"
        stream = open(mode=mode, **kwargs)
        try:
            return io.TextIOWrapper(stream, encoding=encoding,
                                    errors=errors, newline=newline)
        except:
            stream.close()
            raise
#@]

#@ctypes.wintypes[
if os.name == "nt":
    import ctypes.wintypes
#@]

#@rename[
#@requires: mod:os mod:ctypes ctypes.wintypes
def rename(src, dest):
    '''Rename a file (allows overwrites on Windows).'''
    if os.name == "nt":
        MoveFileExW = ctypes.windll.kernel32.MoveFileExW
        MoveFileExW.restype = ctypes.wintypes.BOOL
        MOVEFILE_REPLACE_EXISTING = ctypes.wintypes.DWORD(0x1)
        success = MoveFileExW(ctypes.wintypes.LPCWSTR(src),
                              ctypes.wintypes.LPCWSTR(dest),
                              MOVEFILE_REPLACE_EXISTING)
        if not success:
            raise ctypes.WinError()
    else:
        os.rename(src, dest)
#@]

#@TemporarySaveFile[
#@requires: mod:errno mod:os mod:shutil mod:tempfile rename try_remove wrapped_open
class TemporarySaveFile(object):
    '''A context manager for a saving files atomically.  The context manager
    creates a temporary file to which data may be written.  If the body of the
    `with` statement succeeds, the temporary file is renamed to the target
    filename, overwriting any existing file.  Otherwise, the temporary file is
    deleted.'''

    def __init__(self, filename, mode="w", suffix=None, prefix=None, **kwargs):
        self._fn = filename
        kwargs = dict(kwargs)
        kwargs.update({
            "mode": mode,
            "suffix": ".tmpsave~" if suffix is None else suffix,
            "prefix": (".#" + os.path.basename(filename)).rstrip(".") + "."
                      if prefix is None else prefix,
            "dir": os.path.dirname(filename),
            "delete": False,
        })
        self._kwargs = kwargs

    def __enter__(self):
        if hasattr(self, "_stream"):
            raise ValueError("attempted to __enter__ twice")
        stream = wrapped_open(tempfile.NamedTemporaryFile, **self._kwargs)
        try:
            shutil.copymode(self._fn, stream.name)
        except BaseException as e:
            if not (isinstance(e, OSError) and e.errno == errno.ENOENT):
                try:
                    stream.close()
                finally:
                    try_remove(stream.name)
                raise
        self._stream = stream
        return stream

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self._stream.close()
            if exc_type is None and exc_value is None and traceback is None:
                rename(self._stream.name, self._fn)
            else:
                try_remove(self._stream.name)
        except:
            try_remove(self._stream.name)
            raise
        finally:
            del self._stream
#@]

#@safe_open[
#@requires: mod:io TemporarySaveFile
def safe_open(filename, mode="rt", encoding=None,
              errors=None, newline=None, safe=True):
    truncated_write = "w" in mode and "+" not in mode
    if safe and truncated_write and not isinstance(filename, int):
        open_file = TemporarySaveFile
    else:
        open_file = io.open
    return open_file(filename, mode, encoding=encoding,
                     errors=errors, newline=newline)
#@]

#@save_file[
#@requires: safe_open
def save_file(filename, contents, binary=False, encoding=None,
              errors=None, newline=None, safe=True):
    '''Write the contents to a file.  If `safe` is true, it is performed by
    first writing into a temporary file and then replacing the original file
    with the temporary file.  This ensures that the file will not end up in a
    half-written state.  Note that there is a small possibility that the
    temporary file might remain if the program crashes while writing.'''
    mode = "w" + ("b" if binary else "")
    with safe_open(filename, mode, encoding=encoding,
                   errors=errors, newline=newline, safe=safe) as stream:
        stream.write(contents)
#@]
#@]

#@requires: load_file save_file rename StringIO
#@requires: MappingProxyType reachable_set

try:
    input = raw_input
except NameError:
    pass
input = input

def freeze_arguments(*args, **kwargs):
    return (tuple(args), tuple(sorted(kwargs.items())))

def cached_method(cache_name,
                  normalizer=lambda *args, **kwargs: (args, kwargs)):
    '''Note: arguments must be hashable.'''
    @functools.wraps(cached_method)
    def inner(func):
        @functools.wraps(func)
        def inner(self, *args, **kwargs):
            args, kwargs = normalizer(*args, **kwargs)
            full_args = freeze_arguments(*args, **kwargs)
            try:
                cache = getattr(self, cache_name)
            except AttributeError:
                cache = {}
                setattr(self, cache_name, cache)
            try:
                return cache[full_args]
            except KeyError:
                pass
            value = func(self, *args, **kwargs)
            cache[full_args] = value
            return value
        return inner
    return inner

def invalid_cached_method(self, cache_name, *args, **kwargs):
    cache = getattr(self, cache_name, None)
    full_args = freeze_arguments(*args, **kwargs)
    try:
        del cache[full-args]
    except KeyError:
        pass

def cached_property(func):
    name = "_{0}_cache".format(func.__name__)
    @functools.wraps(func)
    def inner(self):
        try:
            return getattr(self, name)
        except AttributeError:
            pass
        value = func(self)
        setattr(self, name, value)
        return value
    return property(inner)

def realpath_normalizer(fn):
    return (os.path.realpath(fn),), {}

class FileCache(object):

    def __init__(self, load_func):
        '''(FileCache, (filenameStr) -> a) -> a

        load_func is an arbitrary function that returns a value associated
        with the given file.  The cache stores the result of this function.'''
        self._load_func = load_func

    @cached_method("_cache", normalizer=realpath_normalizer)
    def __getitem__(self, fn):
        '''Obtain the cached value for the given file, or run the load_func if
        the file is not yet cached.'''
        return self._load_func(fn)

    def __delitem__(self, fn):
        '''Invalid the cache for the given file.  Has no effect if the file is
        not cached.'''
        invalidate_method_cache(self, "_cache", normalizer=realpath_normalizer)

def json_canonical(data, ensure_ascii=False, sort_keys=True, **kwargs):
    return json.dumps(
        data,
        ensure_ascii=ensure_ascii,
        sort_keys=sort_keys,
        **kwargs
    )

def json_pretty(data, ensure_ascii=False):
    separators = (",", ": ")
    if hasattr(b"", "encode") and ensure_ascii:
        separators = (b",", ": ")
    return json_canonical(data,
                          indent=4,
                          separators=separators,
                          ensure_ascii=ensure_ascii)

def toposort_countrdeps(graph):
    '''Count the number of immediate dependents (reverse dependencies).
    Returns a dict that maps nodes to number of dependents, as well as a list
    of roots (nodes with no dependents).'''
    numrdeps = {}
    for node, deps in graph.items():
        for dep in deps:
            numrdeps[dep] = numrdeps.get(dep, 0) + 1
    roots = []
    for node, deps in graph.items():
        if node not in numrdeps:
            numrdeps[node] = 0
            roots.append(node)
    return numrdeps, roots

def toposort(graph, key=None, reverse=False):
    '''Topologically sort a directed acyclic graph, ensuring that dependents
    are placed after their dependencies, or the reverse if `reverse` is true.

        graph: {node: [node, ...], ...}

    The `graph` is a dictionary of nodes: the key is an arbitrary value that
    uniquely identifies the node, while the value is an iterable of
    dependencies for that node.  For example:

        graph = {0: [1, 2], 1: [2], 2: []}

    This is a graph where 0 depends on both 1 and 2, and 1 depends on 2.

    The sorted result is always deterministic.  However, to achieve this,
    nodes are required to form a total ordering.'''

    # make sure there are no duplicate edges
    graph = dict((node, frozenset(deps)) for node, deps in graph.items())

    # count the number of dependents and extract the roots
    numrdeps, roots = toposort_countrdeps(graph)

    if key is None:
        def key(node):
            '''Sort nodes by the number of immediate dependencies, followed by
            the nodes themselves.'''
            return len(graph[node]), node

    # sort nodes to ensure a deterministic topo-sorted result; current algo
    # sorts by # of immediate dependencies followed by node ID, so nodes with
    # fewer immediate dependencies and/or lower node IDs tend to come first
    roots = sorted(roots, key=key, reverse=reverse)
    graph = dict((node, sorted(deps, key=key, reverse=reverse))
                 for node, deps in graph.items())

    # Kahn's algorithm
    # (note: this will alter numrdeps and roots)
    result = []
    while roots:
        node1 = roots.pop()
        result.append(node1)
        for node2 in graph[node1]:
            numrdeps[node2] -= 1
            if not numrdeps[node2]:
                roots.append(node2)
    if len(result) != len(graph):
        raise ValueError("graph is cyclic")
    if not reverse:
        result.reverse()
    return result
