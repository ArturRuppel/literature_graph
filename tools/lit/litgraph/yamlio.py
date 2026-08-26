"""One YAML parser per thread.

A `ruamel.yaml.YAML` object is not a stateless helper: it holds the scanner, parser and
constructor that walk the document, so two threads calling `load()` on one instance step
through a single state machine together. The result is not a clean error but a torn one —
the exception names whichever file *this* thread was opening while quoting a line from the
file the *other* thread was parsing, so a file that parses fine on its own is reported as
malformed. `lit serve` is a `ThreadingHTTPServer`, and the routes that skip the payload
cache (`/aims.json`, `/preview.html`) each call `build_graph` on their own thread, so two
overlapping requests were enough to fail a build over nothing. A phone opening the mirror
fires exactly that pair.

Thread-local rather than a lock, because a lock would serialise every file read in the repo
behind one mutex to fix a race that a second parser removes outright. The parsers are small
and independent, and there is one per thread for the life of the thread, not one per file.
"""

from __future__ import annotations

import threading

from ruamel.yaml import YAML

_local = threading.local()


def safe_yaml() -> YAML:
    """This thread's `YAML(typ="safe")` — libyaml, fast, read-only. Created on first use."""
    y = getattr(_local, "safe", None)
    if y is None:
        y = _local.safe = YAML(typ="safe")
    return y


def rt_yaml() -> YAML:
    """This thread's round-trip parser, configured exactly as store.py's writes expect:
    quotes preserved, long scalars never re-wrapped, and the `  - {…}` sequence indentation
    the files on disk already use. Created on first use."""
    y = getattr(_local, "rt", None)
    if y is None:
        y = YAML()
        y.preserve_quotes = True
        y.width = 4096
        y.indent(mapping=2, sequence=4, offset=2)
        _local.rt = y
    return y
