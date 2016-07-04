import re

try:
    from types import MappingProxyType as _MappingProxyType
except ImportError:
    def _MappingProxyType(mapping):
        return mapping

class ParseError(Exception):
    def __init__(self, src, row, msg):
        self.src = src
        self.row = row
        self.msg = msg

class Node(object):
    pass

class Text(Node):

    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return "Text({0!r})".format(self.value)

    def to_json(self):
        return self.value

class Attribute(Node):

    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __repr__(self):
        return "Attribute({0!r}, {1!r})".format(self.name, self.value)

    def to_json(self):
        return [self.name, self.value]

class Element(Node):

    def __init__(self, name, children):
        if not isinstance(children, tuple):
            children = tuple(children)
        self.name = name
        self.children = children

    def __repr__(self):
        return "Element({0!r}, {1!r})".format(self.name, self.children)

    @property
    def attributes(self):
        attrs = getattr(self, "_attributes", None)
        if not attrs:
            attrs = {}
            for node in self.children:
                if not isinstance(node, Attribute):
                    continue
                key = node.name
                value = node.value
                attrs[name] = (attrs[name] + "\n"
                               if name in attrs else "") + value
            self._attributes = _MappingProxyType(attrs)
        return attrs

    def to_json(self):
        return [self.name, nodes_to_json(self.children)]

def nodes_to_json(nodes):
    '''
    JSON representation of the document tree:

        node = text_node | attr | elem
        text = "some_text\n"
        attr = ["attr_name", "attr_value"]
        elem = ["elem_name", [node, ...]]
        doc = [node, ...]

    '''
    return [node.to_json() for node in nodes]

def parse_directives(indexed_lines, src):
    for i, line in indexed_lines:
        m = re.match("\s*#@\s*(.*)", line.rstrip("\n"))
        if not m:
            yield i, "line", line
            continue
        directive, = m.groups()
        directive = directive.rstrip()
        if not directive:
            continue
        if directive == "]":
            yield i, "end", None
            continue
        m = re.match("([^[:\s]+)\s*([[:])\s*(.*)", directive)
        if not m:
            raise ParseError(src, i, "invalid directive: " + line.rstrip())
        key, sep, val = m.groups()
        if sep == ":":
            yield i, "attr", (key, val)
        elif sep == "[":
            if val:
                raise ParseError(src, i,
                                 "trailing garbage after '[': " + line.rstrip())
            yield i, "begin", key
        else:
            assert False

def parse_doc(fn):
    with open(fn) as f:
        root_elem = [None, []]
        elem = root_elem
        stack = []
        for i, cmd, data in parse_directives(enumerate(f, 1), fn):
            if cmd == "line":
                elem[1].append(Text(data))
            elif cmd == "attr":
                elem[1].append(Attribute(*data))
            elif cmd == "begin":
                new_elem = [data, []]
                elem[1].append(new_elem)
                stack.append(elem)
                elem = new_elem
            elif cmd == "end":
                try:
                    old_elem = elem
                    elem = stack.pop()
                    elem[1][-1] = Element(*old_elem)
                except IndexError:
                    raise ParseError(fn, i, "unmatched ']'")
            else:
                assert False
    if stack:
        raise ParseError(fn, i, "unclosed '['")
    return root_elem[1]

def render_doc_recursor(out, node):
    if isinstance(node, Text): # text
        out.append(node.value)
    else:
        if len(out) and not out[-1].endswith("\n"):
            # make sure there's a newline before appending directive
            out.append("\n")
        if isinstance(node, Attribute):
            out.append("#@{0}: {1}\n".format(node.name, node.value))
        elif isinstance(node, Element):
            out.append("#@{0}[\n".format(node.name))
            for subnode in node.children:
                render_doc_recursor(out, subnode)
            out.append("#@]\n")
        else:
            raise ValueError("invalid node: " + repr(node))

def render_doc(doc):
    out = []
    for elem in doc:
        render_doc_recursor(out, elem)
    return "".join(out)
