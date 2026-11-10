"""
Automatic Codebase KLOC Scanner for CLEBUGGER
Scans project source trees, counts non-trivial lines of code (KLOC),
categorizes by language, and computes working vs bug KLOC.
"""

import os
from pathlib import Path
from typing import Dict, Any, List

CODE_EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".html": "HTML",
    ".css": "CSS",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".sh": "Shell",
    ".bat": "Batch",
    ".ps1": "PowerShell"
}

IGNORE_DIRS = {
    ".git", ".system_generated", ".gemini", "node_modules",
    "__pycache__", ".pytest_cache", "venv", ".venv",
    "dist", "build", "scratch", "output", "temp", "tmp",
    ".user_uploaded", ".idea", ".vscode"
}

def scan_project_kloc(root_path: str) -> Dict[str, Any]:
    """
    Scans the given directory and returns LOC & KLOC breakdown.
    """
    root = Path(root_path).resolve()
    if not root.exists() or not root.is_dir():
        return {
            "error": f"Path does not exist: {root}",
            "total_loc": 0,
            "total_kloc": 0.0,
            "files_scanned": 0,
            "by_extension": {}
        }

    total_loc = 0
    files_scanned = 0
    by_ext: Dict[str, Dict[str, int]] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if d.lower() not in IGNORE_DIRS and not d.startswith(".")]

        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext in CODE_EXTENSIONS:
                fpath = Path(dirpath) / fname
                try:
                    # Skip large binary or minified files > 2MB
                    if fpath.stat().st_size > 2 * 1024 * 1024:
                        continue
                    
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                    # Count non-empty, non-comment lines
                    lines = [line.strip() for line in text.splitlines()]
                    code_lines = [
                        line for line in lines
                        if line and not line.startswith(("#", "//", "/*", "*", "<!--"))
                    ]
                    count = len(code_lines)

                    total_loc += count
                    files_scanned += 1

                    lang = CODE_EXTENSIONS[ext]
                    if lang not in by_ext:
                        by_ext[lang] = {"files": 0, "loc": 0}
                    by_ext[lang]["files"] += 1
                    by_ext[lang]["loc"] += count
                except Exception:
                    continue

    return {
        "root_path": str(root),
        "total_loc": total_loc,
        "total_kloc": round(total_loc / 1000.0, 3),
        "files_scanned": files_scanned,
        "by_language": by_ext
    }

def collect_project_metrics(project_name: str, build_number: str = "HEAD") -> Dict[str, Any]:
    """
    Scans project on disk, queries active bugs from DB,
    and records an updated KLOC snapshot.
    """
    from db import get_project, get_connection, record_kloc_snapshot

    proj = get_project(project_name)
    if not proj:
        raise ValueError(f"Project '{project_name}' not registered in database")

    scan_res = scan_project_kloc(proj["root_path"])
    total_loc = scan_res["total_loc"]

    # Calculate active bug LOC sum
    conn = get_connection()
    row = conn.execute("""
        SELECT COALESCE(SUM(bug_loc), 0) AS total_bug_loc,
               COUNT(*) AS open_count
        FROM bugs
        WHERE project_name = ? AND status IN ('OPEN', 'IN_PROGRESS', 'REGRESSION')
    """, (project_name,)).fetchone()
    conn.close()

    bug_loc = int(row["total_bug_loc"]) if row else 0
    open_count = int(row["open_count"]) if row else 0

    # Record snapshot in SQLite
    snap = record_kloc_snapshot(
        project_name=project_name,
        build_number=build_number,
        total_loc=total_loc,
        bug_loc=bug_loc
    )

    return {
        "project_name": project_name,
        "build_number": build_number,
        "total_loc": total_loc,
        "total_kloc": snap["total_kloc"],
        "bug_loc": bug_loc,
        "bug_kloc": snap["bug_kloc"],
        "working_loc": snap["working_loc"],
        "working_kloc": snap["working_kloc"],
        "open_bugs_count": open_count,
        "defect_density": snap["defect_density"],
        "scan_details": scan_res
    }
