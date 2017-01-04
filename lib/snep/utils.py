from __future__ import unicode_literals
import functools, json, os

#@imports[
import ctypes
import errno
import heapq
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

#@new_OrdWrapper[
def new_OrdWrapper(key=lambda x: x, reverse=False):
    '''Create a wrapper class that allows a new total ordering to be defined
    on objects of another type.

    'key' is expected to be a key function: it should return a value of some
    totally ordered type that defines the desired ordering.  'reverse'
    determines if the ordering should be reversed.

    The wrapper class defines:

    - a simple constructor that accepts an arbitrary value that can be later
      accessed using '.value', and
    - all 6 of the rich comparison methods.

    '''
    def init_func(self, value):
        self.value = value
        self.key = key(value)
    def repr_func(self):
        return "OrdWrapper({!r})".format(self.value)
    if reverse:
        class OrdWrapper(object):
            __init__ = init_func
            __repr__ = repr_func
            def __lt__(self, other):
                return self.key > other.key
            def __le__(self, other):
                return self.key >= other.key
            def __eq__(self, other):
                return self.key == other.key
            def __ne__(self, other):
                return self.key != other.key
            def __gt__(self, other):
                return self.key < other.key
            def __ge__(self, other):
                return self.key <= other.key
    else:
        class OrdWrapper(object):
            __init__ = init_func
            __repr__ = repr_func
            def __lt__(self, other):
                return self.key < other.key
            def __le__(self, other):
                return self.key <= other.key
            def __eq__(self, other):
                return self.key == other.key
            def __ne__(self, other):
                return self.key != other.key
            def __gt__(self, other):
                return self.key > other.key
            def __ge__(self, other):
                return self.key >= other.key
    return OrdWrapper
#@]

#@toposort[
#@requires: mod:heapq new_OrdWrapper
def toposort(graph, key=lambda x: x, reverse=False, flip=False):
    '''Topologically sort a directed acyclic graph deterministically (see
    caveats below), ensuring that the arrows always point right, unless 'flip'
    is 'True', in which case the arrows always point left.

        <graph> = {<vertex>: [<vertex>, ...], ...}

    The `graph` is represented as a dictionary, where each dictionary key
    uniquely identifies the vertex and its associated value contains a list of
    direct successors for that vertex.  For example:

        graph = {0: [1, 2], 1: [2], 2: [], 3: []}

    This represents a graph with four vertices and three edges:

        0 -> 1
        0 -> 2
        1 -> 2

    Vertex '3' does not have any edges.

    The ordering is determined by the 'key' function, which receives a vertex
    key and produces some totally ordered value.  The ordering can be reversed
    by setting 'reverse' to 'True'.

    The sorted result is always lexicographically minimized, which means it is
    deterministic if and only if the output of 'key' applied to the vertices
    results in distinct values.

    If you originally had an arbitrarily ordered sequence of items and want to
    preserve the original ordering of the elements as much as possible,
    consider using a key function that maps each element to its original
    position.
    '''

    # note: the ordering of the edges is immaterial
    if flip:
        # we must explicitly perform the flip: the lexicographical ordering
        # requirement prevents us from using tricks to avoid this, which would
        # get screwed up by reversing the output of this algorithm
        new_graph = dict((v, set()) for v in graph)
        for v1, vs in graph.items():
            for v2 in vs:
                new_graph[v2].add(v1)
        graph = new_graph
    else:
        graph = dict((v, frozenset(vs)) for v, vs in graph.items())

    # count the number of dependents and extract the roots
    indegree = {}
    for v, deps in graph.items():
        for dep in deps:
            indegree[dep] = indegree.get(dep, 0) + 1
    roots = []
    for v in graph:
        if v not in indegree:
            indegree[v] = 0
            roots.append(v)

    OrdWrapper = new_OrdWrapper(key=key, reverse=reverse)
    roots = [OrdWrapper(v) for v in roots]

    # keep roots sorted to ensure a deterministic result
    heapq.heapify(roots)

    # Kahn's algorithm
    # (note: this will alter indegree and roots)
    result = []
    while roots:
        v1 = heapq.heappop(roots).value
        result.append(v1)
        for v2 in graph[v1]:
            indegree[v2] -= 1
            if not indegree[v2]:
                heapq.heappush(roots, OrdWrapper(v2))
    if len(result) != len(graph):
        raise ValueError("graph is cyclic")

    return result
#@]
#@]

#@requires: load_file save_file rename StringIO
#@requires: MappingProxyType reachable_set toposort

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
