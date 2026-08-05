#!/usr/bin/env python3
"""Standalone static server for the claim-graph prototype.

Serves this directory's static files (index.html, app.js, style.css) and
proxies the graph payload at GET /graph.json from an externally-supplied
path. --graph is required and has no default/fallback: the real data lives
in a private repo and this one is public, so no path is ever committed here.

Usage:
    python3 serve.py --graph /path/to/dist/graph.json [--port 8002]
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
    ap = argparse.ArgumentParser(description="Serve the claim-graph prototype.")
    ap.add_argument("--graph", required=True, help="path to dist/graph.json")
    ap.add_argument("--port", type=int, default=8002)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address; use the tailnet IP to view from another device")
    args = ap.parse_args()

    graph_path = os.path.abspath(args.graph)
    if not os.path.isfile(graph_path):
        raise SystemExit(f"--graph not found: {graph_path}")

    handler = partial(Handler, graph_path=graph_path)
    http.server.ThreadingHTTPServer.allow_reuse_address = True  # survive restarts (TIME_WAIT)
    httpd = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    print(f"claim-graph serving on http://{args.host}:{args.port}  (graph: {graph_path})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
