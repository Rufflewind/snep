from __future__ import unicode_literals
import json

#@imports[
#@]

#@snips[
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

def cached_property(func):
    name = "_{0}_cache".format(func.__name__)
    def inner(self):
        try:
            return getattr(self, name)
        except AttributeError:
            pass
        value = func(self)
        setattr(self, name, value)
        return value
    return property(inner)

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
