from __future__ import unicode_literals
import io, functools, json, os

try:
    StringIO = io.StringIO
except AttributeError:
    import cStringIO
    StringIO = cStringIO.StringIO

#@imports[
#@]

#@snips[
#@safe_open[
#blah
#@]

#@MappingProxyType[
try:
    from types import MappingProxyType
except ImportError:
    def MappingProxyType(mapping):
        return mapping
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
#@]

#@requires: load_file safe_open
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

def toposort_sortnodes(graph, nodes, reverse=False):
    '''Sort nodes by the number of immediate dependencies, followed by the
    nodes themselves.'''
    return sorted(nodes, key=(lambda node: (len(graph[node]), node)),
                  reverse=reverse)

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

def toposort(graph, reverse=False):
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
    graph = dict((node, set(deps)) for node, deps in graph.items())

    # count the number of dependents and extract the roots
    numrdeps, roots = toposort_countrdeps(graph)

    # sort nodes to ensure a deterministic topo-sorted result; current algo
    # sorts by # of immediate dependencies followed by node ID, so nodes with
    # fewer immediate dependencies and/or lower node IDs tend to come first
    roots = toposort_sortnodes(graph, roots, reverse=reverse)
    graph = dict((node, toposort_sortnodes(graph, deps, reverse=reverse))
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
