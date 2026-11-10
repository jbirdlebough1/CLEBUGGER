import urllib.request
import json
import time

time.sleep(1)
base_url = "http://127.0.0.1:8999"

print("1. Testing GET / (Dashboard HTML)")
with urllib.request.urlopen(f"{base_url}/", timeout=5) as r:
    html = r.read().decode("utf-8")
    print(f"   Status: {r.status}, HTML size: {len(html)} bytes")
    assert "CLEBUGGER" in html
    assert "Card 1: Log New Defect" in html
    assert "Card 2: Review Bug Status" in html
    assert "Card 3: Multi-Project Quality Report" in html

print("2. Testing GET /api/projects")
with urllib.request.urlopen(f"{base_url}/api/projects", timeout=5) as r:
    data = json.loads(r.read().decode("utf-8"))
    print(f"   Status: {r.status}, Projects: {[p['name'] for p in data['projects']]}")
    assert len(data["projects"]) >= 1

print("3. Testing GET /api/bugs")
with urllib.request.urlopen(f"{base_url}/api/bugs", timeout=5) as r:
    data = json.loads(r.read().decode("utf-8"))
    print(f"   Status: {r.status}, Bugs count: {len(data['bugs'])}")
    assert len(data["bugs"]) >= 5

print("4. Testing GET /api/summary")
with urllib.request.urlopen(f"{base_url}/api/summary", timeout=5) as r:
    data = json.loads(r.read().decode("utf-8"))
    print(f"   Status: {r.status}, Total KLOC: {data['total_kloc']}, Working: {data['working_kloc']}, Bug: {data['bug_kloc']}")
    assert data["total_kloc"] > 10.0

print("5. Testing GET /api/kloc-trend")
with urllib.request.urlopen(f"{base_url}/api/kloc-trend", timeout=5) as r:
    data = json.loads(r.read().decode("utf-8"))
    print(f"   Status: {r.status}, Snapshots count: {len(data['history'])}")
    assert len(data["history"]) >= 5

print("6. Testing POST /api/bugs (Create bug)")
req = urllib.request.Request(
    f"{base_url}/api/bugs",
    data=json.dumps({
        "project_name": "MEAGCLE",
        "build_number": "v2.4.3-test",
        "title": "Automated verification test bug",
        "status": "OPEN",
        "component": "CI",
        "bug_loc": 10
    }).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=5) as r:
    data = json.loads(r.read().decode("utf-8"))
    print(f"   Status: {r.status}, Created: {data['bug']['bug_code']}")
    test_bug_id = data["bug"]["id"]

print("7. Testing POST /api/bugs/advance (1-click status advance)")
req = urllib.request.Request(
    f"{base_url}/api/bugs/advance",
    data=json.dumps({"id": test_bug_id}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=5) as r:
    data = json.loads(r.read().decode("utf-8"))
    print(f"   Status: {r.status}, Advanced status: {data['bug']['status']}")
    assert data["bug"]["status"] == "IN_PROGRESS"

print("8. Testing PUT /api/bugs (Resolve test bug)")
req = urllib.request.Request(
    f"{base_url}/api/bugs",
    data=json.dumps({"id": test_bug_id, "status": "RESOLVED", "resolution": "Verification complete"}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="PUT"
)
with urllib.request.urlopen(req, timeout=5) as r:
    data = json.loads(r.read().decode("utf-8"))
    print(f"   Status: {r.status}, Resolved: {data['bug']['status']}")
    assert data["bug"]["status"] == "RESOLVED"

print("9. Testing GET /api/export")
with urllib.request.urlopen(f"{base_url}/api/export", timeout=5) as r:
    data = json.loads(r.read().decode("utf-8"))
    print(f"   Status: {r.status}, Exported projects: {len(data['projects'])}, bugs: {len(data['bugs'])}")
    assert "projects" in data and "bugs" in data

print("\nALL 9 TESTS PASSED WITH ZERO DEFECTS!")
