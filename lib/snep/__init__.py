import collections, re
from . import utils

class NonuniqueElementError(KeyError):
    pass

class ParseError(Exception):
    def __init__(self, src, row, msg):
        self.src = src
        self.row = row
        self.msg = msg

Origin = collections.namedtuple("Origin", [
    "filename",
    "line",
    "column",
])

class Node(object):

    def render(self):
        return "".join(self.irender())

    def irender(self):
        raise NotImplemented()

class Text(Node):

    def __init__(self, value, origin=Origin(None, None, None)):
        self.value = value
        self.origin = origin

    def __repr__(self):
        return "Text({0!r})".format(self.value)

    def __eq__(self, other):
        return self._flatten() == other._flatten()

    def __ne__(self, other):
        return self._flatten() != other._flatten()

    def __lt__(self, other):
        return self._flatten() < other._flatten()

    def __le__(self, other):
        return self._flatten() <= other._flatten()

    def __gt__(self, other):
        return self._flatten() > other._flatten()

    def __ge__(self, other):
        return self._flatten() >= other._flatten()

    def __hash__(self):
        return hash(self._flatten())

    def _flatten(self):
        return self.value

    def to_json(self):
        return self.value

    def irender(self):
        yield self.value

class Attribute(Node):

    def __init__(self, name, value, origin=Origin(None, None, None)):
        self.name = name
        self.value = value
        self.origin = origin

    def __repr__(self):
        return "Attribute({0!r}, {1!r})".format(self.name, self.value)

    def __eq__(self, other):
        return self._flatten() == other._flatten()

    def __ne__(self, other):
        return self._flatten() != other._flatten()

    def __lt__(self, other):
        return self._flatten() < other._flatten()

    def __le__(self, other):
        return self._flatten() <= other._flatten()

    def __gt__(self, other):
        return self._flatten() > other._flatten()

    def __ge__(self, other):
        return self._flatten() >= other._flatten()

    def __hash__(self):
        return hash(self._flatten())

    def _flatten(self):
        return self.name, self.value

    def to_json(self):
        return [self.name, self.value]

    def irender(self):
        yield "#@{0}: {1}\n".format(self.name, self.value)

class Element(Node):

    def __init__(self, name, children, origin=Origin(None, None, None),
                 end_comment=""):
        if not isinstance(children, tuple):
            children = tuple(children)
        self.name = name
        self.children = children
        self.origin = origin
        self.end_comment = end_comment

    def __repr__(self):
        return "Element({0!r}, {1!r})".format(self.name, self.children)

    def __eq__(self, other):
        return self._flatten() == other._flatten()

    def __ne__(self, other):
        return self._flatten() != other._flatten()

    def __lt__(self, other):
        return self._flatten() < other._flatten()

    def __le__(self, other):
        return self._flatten() <= other._flatten()

    def __gt__(self, other):
        return self._flatten() > other._flatten()

    def __ge__(self, other):
        return self._flatten() >= other._flatten()

    def __hash__(self):
        return hash(self._flatten())

    def _flatten(self):
        return self.name, self.children

    @utils.cached_property
    def attributes(self):
        '''(Element) -> {nameStr: Element}'''
        attrs = {}
        for node in self.children:
            if not isinstance(node, Attribute):
                continue
            name = node.name
            value = node.value
            attrs[name] = (attrs[name] + "\n"
                           if name in attrs else "") + value
        return utils.MappingProxyType(attrs)

    @utils.cached_property
    def elements(self):
        '''(Element) -> {nameStr: [Element]}

        Return a dict-like object containing all child elements, keyed by
        their names.'''
        elems = {}
        for node in self.children:
            if not isinstance(node, Element):
                continue
            try:
                elems[node.name].append(node)
            except KeyError:
                elems[node.name] = [node]
        return utils.MappingProxyType(elems)

    @utils.cached_property
    def unique_elements(self):
        '''(Element) -> {nameStr: Element}

        Return an OrderedDict containing all child elements whose names are
        unique.'''
        elems = collections.OrderedDict()
        for node in self.children:
            if not isinstance(node, Element):
                continue
            try:
                del elems[node.name]
            except KeyError:
                elems[node.name] = node
        return elems

    @utils.cached_property
    def has_unique_elements(self):
        return len(self.elements) == len(self.unique_elements)

    @utils.cached_property
    def element_indices(self):
        '''(Element) -> {nameStr: [indexInt]}'''
        indices = {}
        for i, node in enumerate(self.children):
            if not isinstance(node, Element):
                continue
            entry = (i, node)
            try:
                indices[node.name].append(i)
            except KeyError:
                indices[node.name] = [i]
        return utils.MappingProxyType(indices)

    def get_element(self, name):
        '''(Element, nameStr) -> Element

        Return the element with the given name.  An error is raised if the
        element does not exist, or its name not unique.'''
        try:
            return self.unique_elements[name]
        except KeyError:
            pass
        if name not in self.elements:
            raise KeyError("element does not exist: {0}".format(name))
        raise NonuniqueElementError("element is not unique: {0}".format(name))

    def replace_name(self, name):
        '''(Element, nameStr) -> Element

        Return a new Element with the same children as self but the provided
        name.'''
        return Element(name, self.children, end_comment=self.end_comment)

    def replace_children(self, children):
        '''(Element, [Node]) -> Element

        Return a new Element with the same name as self but the provided
        children.'''
        return Element(self.name, children, end_comment=self.end_comment)

    def replace_element(self, name, element):
        '''(Element, nameStr, Element) -> Element

        Replace the child element with the given name and return self after
        the modification (self is not altered).  An error is raised if the
        element does not exist, or its name not unique.'''
        self.get_element(name)
        children = list(self.children)
        children[self.element_indices[name][0]] = element
        return self.replace_children(children)

    def replace_element_children(self, name, children):
        '''(Element, nameStr, [Node]) -> Element

        Replace the children of child element with the given name and return
        self after the modification (self is not altered).  An error is raised
        if the element does not exist, or its name not unique.'''
        new_element = self.get_element(name).replace_children(children)
        return self.replace_element(name, new_element)

    def to_json(self):
        '''
        JSON representation of the document tree:

            node = text_node | attr | elem
            text = "some_text\n"
            attr = ["attr_name", "attr_value"]
            elem = ["elem_name", [node, ...]]

        '''
        return [self.name, [child.to_json() for child in self.children]]

    def irender(self):
        if self.name is not None:
            yield "#@{0}[\n".format(self.name)
        for subnode in self.children:
            for chunk in subnode.irender():
                yield chunk
        if self.name is not None:
            yield "#@]{0}\n".format(self.end_comment)

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
        if directive.startswith("]"):
            yield i, "end", directive[1:]
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

def parse_doc_stream(f, fn):
    root_elem = [None, [], Origin(fn, 1, None), ""]
    elem = root_elem
    stack = []
    for i, cmd, data in parse_directives(enumerate(f, 1), fn):
        if cmd == "line":
            elem[1].append(Text(data, origin=Origin(fn, i, None)))
        elif cmd == "attr":
            name, value = data
            elem[1].append(Attribute(name, value,
                                     origin=Origin(fn, i, None)))
        elif cmd == "begin":
            new_elem = [data, [], Origin(fn, i, None), ""]
            elem[1].append(new_elem)
            stack.append(elem)
            elem = new_elem
        elif cmd == "end":
            elem[3] = data
            old_elem = elem
            try:
                elem = stack.pop()
                elem[1][-1] = Element(*old_elem)
            except IndexError:
                raise ParseError(fn, i, "unmatched ']'")
        else:
            assert False
    if stack:
        raise ParseError(fn, i, "unclosed '['")
    return Element(*root_elem)

def parse_doc(s, fn):
    '''Parse the str as a single Element.'''
    with utils.StringIO(s) as f:
        return parse_doc_stream(f, fn)

def parse_doc_file(fn):
    '''Parse the file as a single Element.'''
    with open(fn) as f:
        return parse_doc_stream(f, fn)
