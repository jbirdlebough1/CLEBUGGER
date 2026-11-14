"""
CLEBUGGER Command-Line Interface (CLI)
Query and manage bugs, run KLOC scans, and view metrics directly from the terminal.
Usage:
  python bug.py list [project]
  python bug.py add <project> <title> --build <build> [--loc <loc>] [--comp <comp>]
  python bug.py resolve <bug_code_or_id> <resolution>
  python bug.py scan [project]
  python bug.py kpi
"""

import sys
import argparse
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import db
import kloc_scanner
import github_sync

def cmd_list(args):
    bugs = db.list_bugs(project=args.project if args.project != "ALL" else None)
    if not bugs:
        print("[*] No defects found.")
        return

    print(f"\n{'ID':<10} {'BUILD':<10} {'STATUS':<12} {'LOC':<6} {'TITLE'}")
    print("-" * 75)
    for b in bugs:
        print(f"{b['bug_code']:<10} {b['build_number']:<10} {b['status']:<12} {b['bug_loc']:<6} {b['title'][:36]}")
    print()

def cmd_add(args):
    new_bug = db.create_bug(
        project_name=args.project,
        build_number=args.build,
        title=args.title,
        status=args.status,
        component=args.component,
        bug_loc=args.loc,
        comments=args.comments
    )
    print(f"[+] Created {new_bug['bug_code']} ({new_bug['status']}): {new_bug['title']}")
    # Update scan
    try:
        kloc_scanner.collect_project_metrics(args.project, build_number=args.build)
    except Exception:
        pass

def cmd_resolve(args):
    # Lookup by code or id
    code_or_id = args.id
    target_id = None
    if code_or_id.isdigit():
        target_id = int(code_or_id)
    else:
        conn = db.get_connection()
        row = conn.execute("SELECT id FROM bugs WHERE bug_code = ?", (code_or_id.upper(),)).fetchone()
        conn.close()
        if row:
            target_id = row["id"]

    if not target_id:
        print(f"[-] Bug '{code_or_id}' not found.")
        return

    updated = db.update_bug(target_id, {
        "status": "RESOLVED",
        "resolution": args.resolution
    })
    print(f"[+] Resolved {updated['bug_code']}: {updated['title']}")
    try:
        kloc_scanner.collect_project_metrics(updated["project_name"], build_number=updated["build_number"])
    except Exception:
        pass

def cmd_scan(args):
    projs = [db.get_project(args.project)] if args.project else db.list_projects()
    for p in projs:
        if p:
            print(f"[*] Scanning {p['name']} at {p['root_path']}...")
            res = kloc_scanner.collect_project_metrics(p["name"])
            print(f"    Total: {res['total_kloc']} KLOC | Working: {res['working_kloc']} KLOC | Bug: {res['bug_kloc']} KLOC | Density: {res['defect_density']}")

def cmd_kpi(args):
    conn = db.get_connection()
    projs = db.list_projects()
    total_bugs = conn.execute("SELECT COUNT(*) AS c FROM bugs").fetchone()["c"]
    open_bugs = conn.execute("SELECT COUNT(*) AS c FROM bugs WHERE status IN ('OPEN', 'IN_PROGRESS', 'REGRESSION')").fetchone()["c"]
    resolved_bugs = conn.execute("SELECT COUNT(*) AS c FROM bugs WHERE status IN ('RESOLVED', 'CLOSED')").fetchone()["c"]

    total_kloc = 0.0
    bug_kloc = 0.0
    working_kloc = 0.0

    for p in projs:
        snap = conn.execute("SELECT * FROM kloc_snapshots WHERE project_name = ? ORDER BY id DESC LIMIT 1", (p["name"],)).fetchone()
        if snap:
            total_kloc += snap["total_kloc"]
            bug_kloc += snap["bug_kloc"]
            working_kloc += snap["working_kloc"]
    conn.close()

    density = round(open_bugs / total_kloc, 2) if total_kloc > 0 else 0.0

    print("\n========================================================")
    print("  CLEBUGGER CROSS-PROJECT KPI SUMMARY")
    print("========================================================")
    print(f"  Tracked Projects:  {len(projs)}")
    print(f"  Total Codebase:    {total_kloc:.3f} KLOC")
    print(f"  Working Codebase:  {working_kloc:.3f} KLOC")
    print(f"  Bug Impact:        {bug_kloc:.3f} KLOC")
    print(f"  Active Defects:    {open_bugs}")
    print(f"  Resolved Defects:  {resolved_bugs}")
    print(f"  Defect Density:    {density} bugs/KLOC")
    print("========================================================\n")

def cmd_sync_github(args):
    target = args.project or "JRFK"
    if target.upper() == "ALL":
        github_sync.sync_all()
    else:
        github_sync.sync_project_issues(target)

def main():
    parser = argparse.ArgumentParser(description="CLEBUGGER CLI")
    subparsers = parser.add_subparsers(dest="cmd")

    # list
    p_list = subparsers.add_parser("list")
    p_list.add_argument("project", nargs="?", default="ALL")

    # add
    p_add = subparsers.add_parser("add")
    p_add.add_argument("project")
    p_add.add_argument("title")
    p_add.add_argument("--build", default="HEAD")
    p_add.add_argument("--status", default="OPEN")
    p_add.add_argument("--comp", dest="component", default="")
    p_add.add_argument("--loc", type=int, default=0)
    p_add.add_argument("--comments", default="")

    # resolve
    p_res = subparsers.add_parser("resolve")
    p_res.add_argument("id")
    p_res.add_argument("resolution", default="Fixed and verified")

    # scan
    p_scan = subparsers.add_parser("scan")
    p_scan.add_argument("project", nargs="?", default="")

    # kpi
    subparsers.add_parser("kpi")

    # sync-github
    p_gh = subparsers.add_parser("sync-github")
    p_gh.add_argument("project", nargs="?", default="JRFK")

    args = parser.parse_args()
    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "resolve":
        cmd_resolve(args)
    elif args.cmd == "scan":
        cmd_scan(args)
    elif args.cmd == "kpi":
        cmd_kpi(args)
    elif args.cmd == "sync-github":
        cmd_sync_github(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
