# snep

A basic snippet manager with dependency tracking.

**This is a prototype: things may change and break, so use at your own risk!**

Currently, only Python is supported.  Other languages may be added in the
future.

## Usage

Snippets are written in the markup format as exemplified in
`lib/snep/utils.py`.

To synchronize two files:

~~~
snep sync <file> <file>
~~~

For debugging or exporting to other programs, one can use:

~~~sh
snep to_json
~~~

## What is a snippet manager?

Think of it like a slightly more sophisticated way of copy-pasting code.  It's
intended to be an alternative to libraries.  They are akin to static
libraries, except they are embedded not at link time, but directly into the
source code.

### Advantages of snippets over libraries:

  - Works at the source-code level, so you can do some pretty nifty things
    that aren't otherwise possible through libraries.
  - Don't need to install the library.  Snippets are included as part of the
    source code.
  - No need to worry about systems with libraries that are too old or too new:
    snippets don't change unless you intentionally upgrade them.
  - Easy to small pieces of code without the overhead of package management or
    version control.

### Disadvantages of snippets over libraries:

  - May result in code bloat if multiple libraries use the same snippets.
  - Like static libraries, security vulnerabilities are not automatically
    deliverated through system updates since each package has its own local
    set of snippets.
  - Snippets share the same global scope, so snippets must be written to
    minimize namespace pollution.
  - There is no unique source of "truth": with two clones of the same snippet,
    each is as good as another, and every snippet is an independent entity
    that can evolve by itself.  Two snippets that were once from the same
    ancestor could evolve into something incompatible.
