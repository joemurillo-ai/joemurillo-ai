from __future__ import annotations
import json, urllib.request, html
from datetime import datetime, timezone
from pathlib import Path

OWNER = "joemurillo-ai"
REPO = "aris"
OUT = Path("assets/live-telemetry.svg")

# Public profile telemetry: intentionally limited to public GitHub metadata.
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"joe-profile-telemetry"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

repo = get(f"https://api.github.com/repos/{OWNER}/{REPO}")
commits = get(f"https://api.github.com/repos/{OWNER}/{REPO}/commits?per_page=5")
prs = get(f"https://api.github.com/repos/{OWNER}/{REPO}/pulls?state=open&per_page=100")
issues = get(f"https://api.github.com/repos/{OWNER}/{REPO}/issues?state=open&per_page=100")
issues_only = [x for x in issues if "pull_request" not in x]

latest = commits[0]
sha = latest["sha"][:7]
msg = html.escape(latest["commit"]["message"].splitlines()[0])[:78]
updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="360" viewBox="0 0 1400 360">
<rect width="1400" height="360" rx="26" fill="#0B0F14" stroke="#243142"/>
<text x="70" y="68" fill="#7D8996" font-family="monospace" font-size="20">// LIVE SIGNAL — PUBLIC GITHUB STATE</text>
<circle cx="90" cy="125" r="8" fill="#00FF88"/>
<text x="115" y="133" fill="#E6EDF3" font-family="Arial" font-size="27" font-weight="800">ARIS / {repo["default_branch"].upper()} — ONLINE</text>
<text x="70" y="195" fill="#00E5FF" font-family="monospace" font-size="18">LATEST  {sha}  //  {msg}</text>
<text x="70" y="245" fill="#E6EDF3" font-family="monospace" font-size="18">OPEN PRS  {len(prs):02d}     OPEN ISSUES  {len(issues_only):02d}     REPO SIZE  {repo["size"]} KB</text>
<text x="70" y="303" fill="#7D8996" font-family="monospace" font-size="15">SYNC {updated}  //  PUBLIC METADATA ONLY  //  NO PRIVATE TELEMETRY</text>
</svg>"""
OUT.write_text(svg)
print(f"wrote {OUT}")
