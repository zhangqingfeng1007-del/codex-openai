import cgi
import json
import os
import re
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
TASKS_DIR = ROOT.parent / "data" / "review_tasks"
UPLOADS_DIR = ROOT.parent / "data" / "uploads"
PORT = int(os.environ.get("PORT", "8793"))


class ReviewModuleHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _load_task(self, product_id):
        task_file = TASKS_DIR / f"{product_id}_review_task_v2.json"
        if not task_file.exists():
            return None, task_file
        return json.loads(task_file.read_text(encoding="utf-8")), task_file

    def _save_task(self, task_data, task_file):
        task_file.write_text(json.dumps(task_data, ensure_ascii=False, indent=2), encoding="utf-8")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        m = re.match(r'^/tasks/([^/]+)/file/(.+)$', parsed.path)
        if not m:
            self.send_error(404, "Not Found")
            return
        product_id = m.group(1)
        filename = unquote(m.group(2))

        task_data, task_file = self._load_task(product_id)
        if task_data is None:
            self.send_error(404, f"Task not found: {product_id}")
            return

        pkg = task_data.setdefault("document_package", {"document_package_id": f"pkg_{product_id}_001", "files": []})
        pkg["files"] = [f for f in pkg.get("files", []) if f.get("file_name") != filename]
        self._save_task(task_data, task_file)
        self._send_json({"ok": True, "document_package": pkg})

    def do_POST(self):
        parsed = urlparse(self.path)

        # POST /tasks/{product_id}/upload — multipart file upload
        m = re.match(r'^/tasks/([^/]+)/upload$', parsed.path)
        if m:
            product_id = m.group(1)
            task_data, task_file = self._load_task(product_id)
            if task_data is None:
                self.send_error(404, f"Task not found: {product_id}")
                return

            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.send_error(400, "Expected multipart/form-data")
                return

            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
            )
            if "file" not in form:
                self.send_error(400, "Missing file field")
                return

            file_item = form["file"]
            source_type = form.getvalue("source_type", "other")
            filename = Path(file_item.filename).name  # strip any path component

            upload_dir = UPLOADS_DIR / product_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            save_path = upload_dir / filename
            save_path.write_bytes(file_item.file.read())

            pkg = task_data.setdefault("document_package", {"document_package_id": f"pkg_{product_id}_001", "files": []})
            # Replace existing entry with same filename
            pkg["files"] = [f for f in pkg.get("files", []) if f.get("file_name") != filename]
            pkg["files"].append({
                "source_type": source_type,
                "file_name": filename,
                "parse_quality": "uploaded",
                "local_path": str(save_path),
            })
            self._save_task(task_data, task_file)
            self._send_json({"ok": True, "document_package": pkg})
            return

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
