import json
import os
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
TASKS_DIR = ROOT.parent / "data" / "review_tasks"
PORT = int(os.environ.get("PORT", "8793"))


class ReviewModuleHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/__open":
            self.send_error(404, "Not Found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        file_path = payload.get("path")
        if not file_path:
            self.send_error(400, "Missing path")
            return

        target = Path(file_path).expanduser()
        if not target.exists():
            self.send_error(404, "File not found")
            return

        subprocess.run(["open", str(target)], check=False)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "path": str(target)}).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/__health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "port": PORT}).encode("utf-8"))
            return
        if parsed.path.startswith("/tasks/"):
            product_id = parsed.path[len("/tasks/"):].strip("/")
            task_file = TASKS_DIR / f"{product_id}_review_task_v2.json"
            if not task_file.exists():
                self.send_error(404, f"Task not found: {product_id}")
                return
            data = task_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path == "/standard_values":
            sv_file = ROOT.parent / "data" / "manifests" / "coverage_standard_values_v1.json"
            if not sv_file.exists():
                self.send_error(404, "standard_values file not found")
                return
            raw = json.loads(sv_file.read_text(encoding="utf-8"))
            flat = {}
            for group_fields in raw.get("groups", {}).values():
                for cname, info in group_fields.items():
                    flat[cname] = info.get("values", [])
            for cname, info in raw.get("ungrouped", {}).items():
                flat[cname] = info.get("values", [])
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(flat, ensure_ascii=False).encode("utf-8"))
            return
        if parsed.path == "/tasks":
            files = sorted(TASKS_DIR.glob("*_review_task_v2.json")) if TASKS_DIR.exists() else []
            product_ids = [f.name.replace("_review_task_v2.json", "") for f in files]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"product_ids": product_ids}).encode("utf-8"))
            return
        return super().do_GET()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ReviewModuleHandler)
    print(f"review-module server listening on http://127.0.0.1:{PORT}")
    server.serve_forever()
