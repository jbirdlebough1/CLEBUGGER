"""
CLEBUGGER Standalone Web Server
Serves the Browser-Based Dashboard and REST API for multi-project
bug tracking, SQLite storage, and automatic KLOC metrics.
"""

import sys
import json
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Dict, Any

# Ensure local imports work
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

if sys.stdout is None or sys.stderr is None:
    _log = open(APP_DIR / 'server.log', 'a', encoding='utf-8', buffering=1)
    if sys.stdout is None:
        sys.stdout = _log
    if sys.stderr is None:
        sys.stderr = _log

import db
import kloc_scanner

PORT = 8999

class CLEBuggerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def _send_json(self, data: Any, code: int = 200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        clean_path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Serve index.html as root
        if clean_path in ("/", "/index.html"):
            index_path = APP_DIR / "index.html"
            if index_path.exists():
                content = index_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        # API: List Projects
        if clean_path == "/api/projects":
            projs = db.list_projects()
            self._send_json({"status": "ok", "projects": projs})
            return

        # API: List Bugs
        elif clean_path == "/api/bugs":
            project = query.get("project", ["ALL"])[0]
            status = query.get("status", ["ALL"])[0]
            search = query.get("search", [""])[0]
            bugs = db.list_bugs(project=project, status=status, search=search)
            self._send_json({"status": "ok", "bugs": bugs})
            return

        # API: KLOC Trending History
        elif clean_path == "/api/kloc-trend":
            project = query.get("project", ["ALL"])[0]
            history = db.get_kloc_history(project=project)
            self._send_json({"status": "ok", "history": history})
            return

        # API: Overall Cross-Project Summary & KPIs
        elif clean_path == "/api/summary":
            conn = db.get_connection()
            projs = db.list_projects()
            total_bugs = conn.execute("SELECT COUNT(*) AS c FROM bugs").fetchone()["c"]
            open_bugs = conn.execute("SELECT COUNT(*) AS c FROM bugs WHERE status IN ('OPEN', 'IN_PROGRESS', 'REGRESSION')").fetchone()["c"]
            resolved_bugs = conn.execute("SELECT COUNT(*) AS c FROM bugs WHERE status IN ('RESOLVED', 'CLOSED')").fetchone()["c"]

            # Sum latest snapshot for each project
            total_kloc = 0.0
            bug_kloc = 0.0
            working_kloc = 0.0

            for p in projs:
                pname = p["name"]
                latest_snap = conn.execute("""
                    SELECT * FROM kloc_snapshots
                    WHERE project_name = ?
                    ORDER BY id DESC LIMIT 1
                """, (pname,)).fetchone()
                if latest_snap:
                    total_kloc += latest_snap["total_kloc"]
                    bug_kloc += latest_snap["bug_kloc"]
                    working_kloc += latest_snap["working_kloc"]

            conn.close()

            defect_density = round((open_bugs / total_kloc), 2) if total_kloc > 0 else 0.0
            resolution_rate = round((resolved_bugs / total_bugs * 100.0), 1) if total_bugs > 0 else 100.0

            self._send_json({
                "status": "ok",
                "total_projects": len(projs),
                "total_bugs": total_bugs,
                "open_bugs": open_bugs,
                "resolved_bugs": resolved_bugs,
                "total_kloc": round(total_kloc, 3),
                "bug_kloc": round(bug_kloc, 3),
                "working_kloc": round(working_kloc, 3),
                "defect_density": defect_density,
                "resolution_rate": resolution_rate
            })
            return

        # API: Export Full Database as JSON
        elif clean_path == "/api/export":
            projs = db.list_projects()
            bugs = db.list_bugs()
            history = db.get_kloc_history()
            self._send_json({
                "exported_at": str(APP_DIR),
                "projects": projs,
                "bugs": bugs,
                "kloc_history": history
            })
            return

        # Fallback to standard file server
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        clean_path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            req = json.loads(body)
        except Exception:
            req = {}

        # API: Create / Update Project
        if clean_path == "/api/projects":
            name = req.get("name", "").strip()
            prefix = req.get("code_prefix", "").strip()
            root_path = req.get("root_path", "").strip()
            if not name or not root_path:
                self._send_json({"status": "error", "message": "name and root_path are required"}, 400)
                return

            proj = db.upsert_project(name, prefix, root_path)
            # Trigger immediate scan
            try:
                kloc_scanner.collect_project_metrics(name, build_number="HEAD")
            except Exception as ex:
                print(f"[!] Initial scan warning: {ex}")

            self._send_json({"status": "ok", "project": proj})
            return

        # API: Trigger Automatic KLOC Scan
        elif clean_path == "/api/projects/scan":
            project = req.get("project", "")
            build = req.get("build_number", "HEAD")
            projs_to_scan = [db.get_project(project)] if project else db.list_projects()
            results = []
            for p in projs_to_scan:
                if p:
                    try:
                        metrics = kloc_scanner.collect_project_metrics(p["name"], build_number=build)
                        results.append(metrics)
                    except Exception as e:
                        results.append({"project": p["name"], "error": str(e)})

            self._send_json({"status": "ok", "scanned": results})
            return

        # API: Create Bug
        elif clean_path == "/api/bugs":
            pname = req.get("project_name", "").strip()
            title = req.get("title", "").strip()
            build = req.get("build_number", "v1.0.0").strip()
            if not pname or not title:
                self._send_json({"status": "error", "message": "project_name and title are required"}, 400)
                return

            new_bug = db.create_bug(
                project_name=pname,
                build_number=build,
                title=title,
                status=req.get("status", "OPEN"),
                component=req.get("component", ""),
                affected_files=req.get("affected_files", ""),
                bug_loc=int(req.get("bug_loc", 0)),
                resolution=req.get("resolution", ""),
                comments=req.get("comments", "")
            )

            # Auto re-calculate KLOC snapshot
            try:
                kloc_scanner.collect_project_metrics(pname, build_number=build)
            except Exception as ex:
                print(f"[!] KLOC scan after bug creation notice: {ex}")

            self._send_json({"status": "ok", "bug": new_bug})
            return

        # API: 1-Click Status Advance
        elif clean_path == "/api/bugs/advance":
            bug_id = int(req.get("id", 0))
            current = db.get_bug(bug_id)
            if not current:
                self._send_json({"status": "error", "message": "Bug not found"}, 404)
                return

            # Cycle: OPEN -> IN_PROGRESS -> RESOLVED -> CLOSED -> REGRESSION -> OPEN
            cycle = {
                "OPEN": "IN_PROGRESS",
                "IN_PROGRESS": "RESOLVED",
                "RESOLVED": "CLOSED",
                "CLOSED": "REGRESSION",
                "REGRESSION": "IN_PROGRESS"
            }
            next_status = cycle.get(current["status"], "OPEN")
            updated = db.update_bug(bug_id, {"status": next_status})

            try:
                kloc_scanner.collect_project_metrics(current["project_name"], build_number=current["build_number"])
            except Exception:
                pass

            self._send_json({"status": "ok", "bug": updated})
            return

        self._send_json({"status": "error", "message": "Endpoint not found"}, 404)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        clean_path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            req = json.loads(body)
        except Exception:
            req = {}

        if clean_path == "/api/bugs":
            bug_id = int(req.get("id", 0))
            if not bug_id:
                self._send_json({"status": "error", "message": "id is required"}, 400)
                return

            updated = db.update_bug(bug_id, req)
            if updated:
                try:
                    kloc_scanner.collect_project_metrics(updated["project_name"], build_number=updated["build_number"])
                except Exception:
                    pass
                self._send_json({"status": "ok", "bug": updated})
            else:
                self._send_json({"status": "error", "message": "Bug not found"}, 404)
            return

        self._send_json({"status": "error", "message": "Endpoint not found"}, 404)

def run_server(port: int = PORT):
    db.init_db()
    server_address = ("127.0.0.1", port)
    HTTPServer.allow_reuse_address = True
    httpd = HTTPServer(server_address, CLEBuggerHandler)
    print(f"[*] CLEBUGGER running at http://127.0.0.1:{port}/")
    print(f"[*] Database file: {db.DB_PATH}")
    while True:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Server stopped.")
            break
        except Exception as e:
            print(f"[!] Server exception: {e}")
            time.sleep(0.5)

if __name__ == "__main__":
    p = PORT
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        p = int(sys.argv[1])
    run_server(p)
