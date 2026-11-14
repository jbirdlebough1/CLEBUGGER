"""
GitHub Issues Synchronizer for CLEBUGGER
Fetches issues from GitHub repositories and automatically creates/updates
defects in the CLEBUGGER SQLite database.
"""

import sys
import os
import re
import json
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import db
import kloc_scanner

def get_repo_slug_from_git(root_path: str) -> Optional[str]:
    """
    Attempts to extract 'owner/repo' from git remotes 'github' or 'origin'.
    """
    root = Path(root_path)
    if not (root / ".git").exists():
        return None

    for remote_name in ("github", "origin"):
        try:
            res = subprocess.run(
                ["git", "-C", str(root), "remote", "get-url", remote_name],
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode == 0:
                url = res.stdout.strip()
                # Matches https://github.com/owner/repo(.git)? or git@github.com:owner/repo(.git)?
                match = re.search(r"github\.com[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$", url)
                if match:
                    return f"{match.group(1)}/{match.group(2)}"
        except Exception:
            continue
    return None

def fetch_github_issues(repo_slug: str, state: str = "all") -> List[Dict[str, Any]]:
    """
    Queries GitHub REST API for issues in the given repository.
    """
    url = f"https://api.github.com/repos/{repo_slug}/issues?state={state}&per_page=100"
    headers = {
        "User-Agent": "CLEBugger-Sync/1.0",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Check for optional GITHUB_TOKEN environment variable
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # Filter out pull requests (GitHub issues API includes PRs with a 'pull_request' key)
            issues = [item for item in data if "pull_request" not in item]
            return issues
    except urllib.error.HTTPError as e:
        print(f"[-] HTTP Error querying GitHub ({url}): {e.code} {e.reason}")
        return []
    except Exception as e:
        print(f"[-] Error querying GitHub ({url}): {e}")
        return []

def sync_project_issues(project_name: str, repo_slug: Optional[str] = None) -> Dict[str, Any]:
    """
    Synchronizes GitHub issues for a specific project into CLEBUGGER.
    """
    proj = db.get_project(project_name)
    if not proj:
        print(f"[-] Project '{project_name}' not found in CLEBugger.")
        return {"project": project_name, "created": 0, "updated": 0, "error": "Project not found"}

    if not repo_slug:
        repo_slug = get_repo_slug_from_git(proj["root_path"])

    if not repo_slug:
        print(f"[-] Could not determine GitHub repository for project '{project_name}' ({proj['root_path']}).")
        return {"project": project_name, "created": 0, "updated": 0, "error": "No GitHub repo detected"}

    print(f"[*] Syncing GitHub issues for '{project_name}' from {repo_slug}...")
    issues = fetch_github_issues(repo_slug, state="all")
    print(f"[*] Fetched {len(issues)} issue(s) from GitHub.")

    existing_bugs = db.list_bugs(project=project_name)
    created_count = 0
    updated_count = 0

    conn = db.get_connection()

    for issue in issues:
        issue_num = issue["number"]
        issue_title = issue["title"]
        issue_state = issue["state"]  # "open" or "closed"
        issue_url = issue["html_url"]
        issue_body = issue.get("body") or ""
        labels = [l["name"] for l in issue.get("labels", [])]
        comp_tag = ", ".join(labels) if labels else "GitHub"

        # Check if already tracked by searching for [GH#<number>]
        gh_tag = f"[GH#{issue_num}]"
        matched_bug = None
        for b in existing_bugs:
            if gh_tag in b["title"] or f"issues/{issue_num}" in (b["comments"] or ""):
                matched_bug = b
                break

        if matched_bug:
            # Check if status needs synchronization
            target_status = "RESOLVED" if issue_state == "closed" else matched_bug["status"]
            if issue_state == "closed" and matched_bug["status"] in ("OPEN", "IN_PROGRESS"):
                db.update_bug(matched_bug["id"], {
                    "status": "RESOLVED",
                    "resolution": f"Closed upstream on GitHub ({issue_url})"
                })
                print(f"[~] Resolved existing defect {matched_bug['bug_code']} (GitHub issue #{issue_num} closed)")
                updated_count += 1
        else:
            # Create new defect in CLEBugger
            init_status = "RESOLVED" if issue_state == "closed" else "OPEN"
            resolution_text = f"Closed upstream on GitHub ({issue_url})" if issue_state == "closed" else ""
            comment_text = (
                f"Imported from GitHub Issue #{issue_num}: {issue_url}\n"
                f"Author: {issue.get('user', {}).get('login', 'unknown')}\n\n"
                f"{issue_body}"
            )
            new_title = f"{gh_tag} {issue_title}"

            new_bug = db.create_bug(
                project_name=project_name,
                build_number="v01.00.00-beta",
                title=new_title,
                status=init_status,
                component=comp_tag,
                bug_loc=20,  # Default estimate for external reports
                resolution=resolution_text,
                comments=comment_text
            )
            print(f"[+] Created {new_bug['bug_code']} ({init_status}) from GitHub Issue #{issue_num}: {issue_title}")
            created_count += 1

    conn.close()

    # Recalculate metrics
    try:
        metrics = kloc_scanner.collect_project_metrics(project_name, build_number="v01.00.00-beta")
        print(f"[+] Metrics refreshed: {metrics['working_kloc']} Working KLOC, Defect Density: {metrics['defect_density']}")
    except Exception as e:
        print(f"[!] Warning: failed to refresh KLOC metrics: {e}")

    return {
        "project": project_name,
        "repo": repo_slug,
        "total_issues": len(issues),
        "created": created_count,
        "updated": updated_count
    }

def sync_all():
    """
    Syncs GitHub issues for all registered projects.
    """
    projects = db.list_projects()
    summary = []
    for p in projects:
        res = sync_project_issues(p["name"])
        summary.append(res)
    return summary

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "JRFK"
    if target.upper() == "ALL":
        sync_all()
    else:
        sync_project_issues(target)
