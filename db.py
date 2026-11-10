"""
CLEBUGGER Database Layer
SQLite3 persistent storage for multi-project bug tracking,
regression history, and automatic KLOC metrics.
"""

import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
import datetime

DB_DIR = Path(__file__).resolve().parent
DB_PATH = DB_DIR / "bugs.db"

def get_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_connection()
    with conn:
        # Projects table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                code_prefix TEXT NOT NULL,
                root_path TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Bugs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bugs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                bug_number INTEGER NOT NULL,
                bug_code TEXT NOT NULL,
                build_number TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                component TEXT DEFAULT '',
                affected_files TEXT DEFAULT '',
                bug_loc INTEGER DEFAULT 0,
                resolution TEXT DEFAULT '',
                comments TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME,
                UNIQUE(project_name, bug_number)
            );
        """)

        # KLOC Historical Snapshots table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kloc_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                build_number TEXT NOT NULL,
                total_loc INTEGER NOT NULL,
                total_kloc REAL NOT NULL,
                bug_loc INTEGER NOT NULL,
                bug_kloc REAL NOT NULL,
                working_loc INTEGER NOT NULL,
                working_kloc REAL NOT NULL,
                open_bugs_count INTEGER NOT NULL,
                defect_density REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Indices
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bugs_proj ON bugs(project_name);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_kloc_proj ON kloc_snapshots(project_name);")
    conn.close()

# --- Project Operations ---
def upsert_project(name: str, code_prefix: str, root_path: str) -> Dict[str, Any]:
    conn = get_connection()
    clean_name = name.strip()
    prefix = code_prefix.strip().upper() or clean_name[:3].upper()
    with conn:
        conn.execute("""
            INSERT INTO projects (name, code_prefix, root_path)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                code_prefix = excluded.code_prefix,
                root_path = excluded.root_path;
        """, (clean_name, prefix, str(Path(root_path).resolve())))
    conn.close()
    return get_project(clean_name)

def get_project(name: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
    conn.close()
    return dict(row) if row else None

def list_projects() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM projects ORDER BY name ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Bug Operations ---
def create_bug(project_name: str, build_number: str, title: str,
               status: str = "OPEN", component: str = "",
               affected_files: str = "", bug_loc: int = 0,
               resolution: str = "", comments: str = "") -> Dict[str, Any]:
    conn = get_connection()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Get project prefix
    proj = get_project(project_name)
    prefix = proj["code_prefix"] if proj else project_name[:3].upper()

    with conn:
        # Determine next bug_number for this project
        row = conn.execute(
            "SELECT COALESCE(MAX(bug_number), 0) + 1 AS next_num FROM bugs WHERE project_name = ?",
            (project_name,)
        ).fetchone()
        next_num = row["next_num"]
        bug_code = f"{prefix}-{next_num:03d}"

        resolved_at = now_str if status in ("RESOLVED", "CLOSED") else None

        conn.execute("""
            INSERT INTO bugs (
                project_name, bug_number, bug_code, build_number,
                title, status, component, affected_files,
                bug_loc, resolution, comments, created_at, updated_at, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_name, next_num, bug_code, build_number,
            title, status, component, affected_files,
            bug_loc, resolution, comments, now_str, now_str, resolved_at
        ))
        bug_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    conn.close()
    return get_bug(bug_id)

def update_bug(bug_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    allowed = {
        "build_number", "title", "status", "component",
        "affected_files", "bug_loc", "resolution", "comments"
    }
    set_clauses = []
    values = []
    for k, v in updates.items():
        if k in allowed:
            set_clauses.append(f"{k} = ?")
            values.append(v)

    if not set_clauses:
        conn.close()
        return get_bug(bug_id)

    set_clauses.append("updated_at = ?")
    values.append(now_str)

    if "status" in updates:
        if updates["status"] in ("RESOLVED", "CLOSED"):
            set_clauses.append("resolved_at = ?")
            values.append(now_str)
        elif updates["status"] in ("OPEN", "IN_PROGRESS", "REGRESSION"):
            set_clauses.append("resolved_at = NULL")

    values.append(bug_id)
    with conn:
        conn.execute(f"UPDATE bugs SET {', '.join(set_clauses)} WHERE id = ?", tuple(values))

    conn.close()
    return get_bug(bug_id)

def get_bug(bug_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM bugs WHERE id = ?", (bug_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def list_bugs(project: Optional[str] = None, status: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    query = "SELECT * FROM bugs WHERE 1=1"
    params = []
    if project and project != "ALL":
        query += " AND project_name = ?"
        params.append(project)
    if status and status != "ALL":
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (title LIKE ? OR comments LIKE ? OR resolution LIKE ? OR bug_code LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term])

    query += " ORDER BY id DESC"
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- KLOC Snapshots ---
def record_kloc_snapshot(project_name: str, build_number: str, total_loc: int, bug_loc: int) -> Dict[str, Any]:
    conn = get_connection()
    total_kloc = round(total_loc / 1000.0, 3)
    bug_kloc = round(bug_loc / 1000.0, 3)
    working_loc = max(0, total_loc - bug_loc)
    working_kloc = round(working_loc / 1000.0, 3)

    # Count open bugs
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM bugs WHERE project_name = ? AND status IN ('OPEN', 'IN_PROGRESS', 'REGRESSION')",
        (project_name,)
    ).fetchone()
    open_count = row["c"] if row else 0

    defect_density = round((open_count / total_kloc), 2) if total_kloc > 0 else 0.0

    with conn:
        conn.execute("""
            INSERT INTO kloc_snapshots (
                project_name, build_number, total_loc, total_kloc,
                bug_loc, bug_kloc, working_loc, working_kloc,
                open_bugs_count, defect_density
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_name, build_number, total_loc, total_kloc,
            bug_loc, bug_kloc, working_loc, working_kloc,
            open_count, defect_density
        ))
        snap_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    row = conn.execute("SELECT * FROM kloc_snapshots WHERE id = ?", (snap_id,)).fetchone()
    conn.close()
    return dict(row)

def get_kloc_history(project: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    if project and project != "ALL":
        rows = conn.execute(
            "SELECT * FROM kloc_snapshots WHERE project_name = ? ORDER BY id ASC",
            (project,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM kloc_snapshots ORDER BY id ASC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Auto-initialize on import
init_db()
