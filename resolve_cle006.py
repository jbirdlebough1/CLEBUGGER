import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import db
import kloc_scanner

res_text = (
    "Fixed unescaped quote in applyBatchToolPreset JS string (changed to 1/8-in Endmill). "
    "In Python f-strings, 1/8\\\" evaluated to literal 1/8\" in JS, throwing a parse-time "
    "SyntaxError that halted script execution before initReliefTuner() could run, hanging all "
    "buttons and leaving 'Checking project...' on screen."
)

updated = db.update_bug(7, {
    "status": "RESOLVED",
    "resolution": res_text,
    "affected_files": "core/server.py:6802",
    "bug_loc": 1
})

kloc_scanner.collect_project_metrics("MEAGCLE", build_number="v2.4.3")
print(f"[+] Resolved: {updated['bug_code']} ({updated['status']}): {updated['title']}")
