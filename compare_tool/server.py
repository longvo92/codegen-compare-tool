"""Local web server: JSON API + single-page UI. Binds 127.0.0.1 only."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .report import build_report
from .scanner import read_text, summarize

UI_FILE = Path(__file__).parent / 'ui' / 'index.html'


def make_handler(results, old_root, new_root):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silence per-request console spam
            pass

        def _send(self, code, ctype, body):
            if isinstance(body, str):
                body = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', ctype + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj):
            self._send(200, 'application/json', json.dumps(obj))

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == '/' or url.path == '/index.html':
                self._send(200, 'text/html', UI_FILE.read_text(encoding='utf-8'))
            elif url.path == '/api/tree':
                files = [{'path': p,
                          'status': r['status'],
                          'notes': r['notes'],
                          'binary': r['binary']}
                         for p, r in sorted(results.items())]
                self._json({'old_root': str(old_root), 'new_root': str(new_root),
                            'summary': summarize(results), 'files': files})
            elif url.path == '/api/diff':
                qs = parse_qs(url.query)
                rel = qs.get('path', [''])[0]
                r = results.get(rel)
                if r is None:
                    self._send(404, 'text/plain', 'unknown path')
                    return
                old_p = Path(old_root) / rel
                new_p = Path(new_root) / rel
                old_lines = (read_text(old_p).split('\n')
                             if old_p.is_file() and not r['binary'] else [])
                new_lines = (read_text(new_p).split('\n')
                             if new_p.is_file() and not r['binary'] else [])
                self._json({'path': rel, 'status': r['status'], 'binary': r['binary'],
                            'notes': r['notes'], 'renames': r['renames'],
                            'hunks': r['hunks'],
                            'old_lines': old_lines, 'new_lines': new_lines})
            elif url.path == '/api/report':
                html_doc = build_report(results, old_root, new_root)
                self._send(200, 'text/html', html_doc)
            else:
                self._send(404, 'text/plain', 'not found')

    return Handler


def serve(results, old_root, new_root, port):
    handler = make_handler(results, old_root, new_root)
    httpd = ThreadingHTTPServer(('127.0.0.1', port), handler)
    return httpd
