#!/usr/bin/env python3
"""Static server for the paper-graph prototype (View A, §2 of
docs/2026-08-05-additive-graph-views.md). stdlib only, no deps.

Serves this directory's static files plus the graph.json payload from
wherever --graph points (the private data repo — never hardcoded here).
"""
import argparse
import http.server
import os
from functools import partial
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    """This directory's files, with /graph.json mapped onto the --graph path.

    Mapping the *path* rather than overriding do_GET keeps the stdlib's
    content-type, Last-Modified, HEAD and 304 handling, and streams the file
    instead of buffering a multi-megabyte payload per request. All three
    prototypes share this shape on purpose — reading one teaches all three —
    while each stays standalone: stdlib only, copy the folder and it runs."""

    def __init__(self, *a, graph_path=None, **kw):
        self.graph_path = graph_path
        super().__init__(*a, directory=HERE, **kw)

    def translate_path(self, path):
        if urlparse(path).path == "/graph.json":
            return self.graph_path
        return super().translate_path(path)

    def log_message(self, fmt, *args):
        pass  # keep stdout quiet; errors still raise


def main():
    p = argparse.ArgumentParser(description="Serve the paper-graph prototype.")
    p.add_argument("--graph", required=True, help="Path to graph.json (private data repo)")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--host", default="127.0.0.1",
                   help="bind address; use the tailnet IP to view from another device")
    args = p.parse_args()

    graph_path = os.path.abspath(args.graph)
    if not os.path.isfile(graph_path):
        raise SystemExit(f"--graph not found: {graph_path}")

    handler = partial(Handler, graph_path=graph_path)
    # Threading, not plain TCPServer: a single-threaded server stalls the whole page
    # behind one slow request, which a 3.6 MB graph.json over the tailnet reliably is.
    http.server.ThreadingHTTPServer.allow_reuse_address = True  # survive restarts (TIME_WAIT)
    httpd = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    print(f"paper-graph serving on http://{args.host}:{args.port}  (graph={graph_path})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
