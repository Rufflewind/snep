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
