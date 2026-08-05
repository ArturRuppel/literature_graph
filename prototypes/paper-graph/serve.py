#!/usr/bin/env python3
"""Static server for the paper-graph prototype (View A, §2 of
docs/2026-08-05-additive-graph-views.md). stdlib only, no deps.

Serves this directory's static files plus the graph.json payload from
wherever --graph points (the private data repo — never hardcoded here).
"""
import argparse
import http.server
import os
import socketserver
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))


def make_handler(graph_path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=HERE, **kwargs)

        def translate_path(self, path):
            if urlparse(path).path == "/graph.json":
                return graph_path
            return super().translate_path(path)

        def log_message(self, fmt, *args):
            pass  # keep stdout quiet; errors still raise

    return Handler


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

    handler = make_handler(graph_path)
    socketserver.TCPServer.allow_reuse_address = True  # survive quick restarts (TIME_WAIT)
    with socketserver.TCPServer((args.host, args.port), handler) as httpd:
        print(f"paper-graph serving on http://{args.host}:{args.port}  (graph={graph_path})")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
