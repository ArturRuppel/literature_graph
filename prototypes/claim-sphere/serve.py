#!/usr/bin/env python3
"""Standalone static server for the claim-sphere prototype.

Serves this directory's static files (index.html, app.js, model.js, scene.js,
style.css, vendor/) and proxies the graph payload at GET /graph.json from an
externally-supplied path. --graph is required and has no default/fallback:
the real data lives in a private repo and this one is public, so no path is
ever committed here.

Usage:
    python3 serve.py --graph /path/to/dist/graph.json [--port 8003]
"""
import argparse
import http.server
import os
from functools import partial

HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, graph_path=None, **kw):
        self.graph_path = graph_path
        super().__init__(*a, **kw)

    def do_GET(self):
        if self.path == "/graph.json":
            try:
                with open(self.graph_path, "rb") as f:
                    body = f.read()
            except OSError as e:
                self.send_error(500, f"could not read --graph file: {e}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True, help="path to dist/graph.json")
    ap.add_argument("--port", type=int, default=8003)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    handler = partial(Handler, directory=HERE, graph_path=os.path.abspath(args.graph))
    httpd = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    print(f"claim-sphere serving on http://{args.host}:{args.port}  (graph: {args.graph})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
