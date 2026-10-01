"""Serve the real client with a local fixture API config, without changing web/config.js."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(WEB), **kwargs)
    def do_GET(self):
        resource=self.path.split("?",1)[0]
        if resource in {"/config.js", "/__fixtures.json"}:
            body = (b'window.TABLETOP_API_URL="http://127.0.0.1:8776";' if resource=="/config.js" else
                    (WEB.parent / "data/player-view-verification/fixtures.json").read_bytes())
            self.send_response(200)
            self.send_header("Content-Type","application/javascript" if resource=="/config.js" else "application/json")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else: super().do_GET()
    def log_message(self,*args): pass

ThreadingHTTPServer(("127.0.0.1",8098),Handler).serve_forever()
