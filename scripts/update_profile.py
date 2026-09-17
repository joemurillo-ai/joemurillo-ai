from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OWNER = "joemurillo-ai"
README = Path("README.md")
SVG_OUT = Path("assets/live-command.svg")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

REPOS = [
    ("aris", "ARIS"),
    ("xoris-ai", "XORIS"),
    ("pcap-triage-pipeline", "PCAP TRIAGE"),
    ("azure-ai-security-briefing-agent", "SECURITY BRIEFING"),
    ("humanexe", "HUMAN.EXE"),
]


def api(path: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "joe-command-profile-v3",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(f"https://api.github.com{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print(f"WARN {path}: {exc}")
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def ago(iso: str | None) -> str:
    dt = parse_dt(iso)
    if not dt:
        return "n/a"
    delta = now_utc() - dt
    if delta.days >= 1:
        return f"{delta.days}d ago"
    hours = max(0, int(delta.total_seconds() // 3600))
    if hours >= 1:
        return f"{hours}h ago"
    mins = max(0, int(delta.total_seconds() // 60))
    return f"{mins}m ago"


def clean(text: str, limit: int = 72) -> str:
    text = re.sub(r"\s+", " ", text.strip()).replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def latest_ci(repo: str) -> tuple[str, str]:
    runs = api(f"/repos/{OWNER}/{repo}/actions/runs?per_page=1")
    if not runs or not runs.get("workflow_runs"):
        return "—", "none"
    run = runs["workflow_runs"][0]
    status = run.get("status") or "unknown"
    if status != "completed":
        return status.upper(), status
    conclusion = run.get("conclusion") or "unknown"
    return conclusion.upper(), conclusion


def commit_count(repo: str, days: int) -> int:
    since = (now_utc() - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    path = f"/repos/{OWNER}/{repo}/commits?since={urllib.parse.quote(since)}&per_page=100"
    commits = api(path) or []
    return len(commits)


def snapshot(repo: str, label: str) -> dict:
    meta = api(f"/repos/{OWNER}/{repo}") or {}
    commits = api(f"/repos/{OWNER}/{repo}/commits?per_page=5") or []
    pulls = api(f"/repos/{OWNER}/{repo}/pulls?state=open&per_page=100") or []
    issues = api(f"/repos/{OWNER}/{repo}/issues?state=open&per_page=100") or []
    real_issues = [i for i in issues if "pull_request" not in i]
    last = commits[0] if commits else {}
    last_date = last.get("commit", {}).get("committer", {}).get("date")
    ci_label, ci_raw = latest_ci(repo)
    return {
        "repo": repo,
        "label": label,
        "branch": meta.get("default_branch", "—"),
        "sha": (last.get("sha") or "—")[:7],
        "last_date": last_date,
        "open_prs": len(pulls),
        "open_issues": len(real_issues),
        "ci": ci_label,
        "ci_raw": ci_raw,
        "commits": commits,
        "c7": commit_count(repo, 7),
        "c30": commit_count(repo, 30),
    }


def status_for(s: dict) -> str:
    if s["ci_raw"] in {"failure", "timed_out", "cancelled", "action_required"}:
        return "ATTENTION"
    dt = parse_dt(s["last_date"])
    if not dt:
        return "UNKNOWN"
    age = (now_utc() - dt).days
    if age <= 14:
        return "ACTIVE"
    if age <= 90:
        return "WARM"
    return "QUIET"


def telemetry_block(snaps: list[dict]) -> str:
    rows = []
    for s in snaps:
        rows.append(
            f"| [{s['label']}](https://github.com/{OWNER}/{s['repo']}) | `{s['branch']}` | `{s['sha']}` | "
            f"{ago(s['last_date'])} | {s['c7']} | {s['open_prs']} | {s['open_issues']} | {s['ci']} | {status_for(s)} |"
        )
    synced = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join([
        "<!-- V23:TELEMETRY:START -->",
        "| System | Branch | Head | Last commit | 7d commits | PRs | Issues | Latest Action | Signal |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
        *rows,
        "",
        f"`telemetry_sync: {synced}`  ",
        "`boundary: public GitHub metadata only`",
        "<!-- V23:TELEMETRY:END -->",
    ])


def mission_log_block(snaps: list[dict]) -> str:
    events = []
    for s in snaps:
        for commit in s["commits"]:
            c = commit.get("commit", {})
            date = c.get("committer", {}).get("date")
            if not date:
                continue
            events.append({
                "date": date,
                "repo": s["repo"],
                "sha": (commit.get("sha") or "")[:7],
                "message": clean(c.get("message", "").splitlines()[0]),
                "url": commit.get("html_url", "#"),
            })
    events.sort(key=lambda x: x["date"], reverse=True)
    lines = [
        "<!-- V23:MISSION_LOG:START -->",
        "| UTC | System | Mission event | Commit |",
        "|---|---|---|---|",
    ]
    for event in events[:12]:
        dt = parse_dt(event["date"])
        stamp = dt.strftime("%Y-%m-%d %H:%M") if dt else "—"
        lines.append(
            f"| {stamp} | `{event['repo']}` | {event['message']} | [`{event['sha']}`]({event['url']}) |"
        )
    lines.append("<!-- V23:MISSION_LOG:END -->")
    return "\n".join(lines)


def pulse_block(snaps: list[dict]) -> str:
    c7 = sum(s["c7"] for s in snaps)
    c30 = sum(s["c30"] for s in snaps)
    active30 = sum(1 for s in snaps if s["c30"] > 0)
    passing = sum(1 for s in snaps if s["ci_raw"] == "success")
    attention = sum(1 for s in snaps if status_for(s) == "ATTENTION")
    prs = sum(s["open_prs"] for s in snaps)
    issues = sum(s["open_issues"] for s in snaps)
    return "\n".join([
        "<!-- V3:PULSE:START -->",
        "```text",
        "PORTFOLIO PULSE",
        "------------------------------------------------------------",
        f"commits_7d       {c7}",
        f"commits_30d      {c30}",
        f"active_repos_30d {active30}/{len(snaps)}",
        f"ci_success       {passing}",
        f"attention        {attention}",
        f"open_prs         {prs}",
        f"open_issues      {issues}",
        "````".replace("````", "```"),
        "<!-- V3:PULSE:END -->",
    ])


def render_svg(snaps: list[dict]) -> None:
    c7 = sum(s["c7"] for s in snaps)
    c30 = sum(s["c30"] for s in snaps)
    active30 = sum(1 for s in snaps if s["c30"] > 0)
    passing = sum(1 for s in snaps if s["ci_raw"] == "success")
    attention = sum(1 for s in snaps if status_for(s) == "ATTENTION")
    stamp = now_utc().strftime("%Y-%m-%d %H:%M UTC")

    cards = [
        ("COMMITS / 7D", str(c7)),
        ("COMMITS / 30D", str(c30)),
        ("ACTIVE REPOS", f"{active30}/{len(snaps)}"),
        ("CI SUCCESS", str(passing)),
        ("ATTENTION", str(attention)),
    ]
    card_svg = []
    for i, (label, value) in enumerate(cards):
        x = 36 + i * 226
        card_svg.append(f'''<rect x="{x}" y="116" width="202" height="96" rx="12" fill="#111827" stroke="#273449"/>
<text x="{x+16}" y="145" fill="#7DD3FC" font-size="13" font-family="monospace">{html.escape(label)}</text>
<text x="{x+16}" y="188" fill="#F8FAFC" font-size="34" font-weight="700" font-family="monospace">{html.escape(value)}</text>''')

    repo_lines = []
    y = 260
    for s in snaps:
        sig = status_for(s)
        color = "#22C55E" if sig == "ACTIVE" else "#F59E0B" if sig in {"WARM", "ATTENTION"} else "#94A3B8"
        repo_lines.append(
            f'<circle cx="54" cy="{y-5}" r="5" fill="{color}"/>'
            f'<text x="70" y="{y}" fill="#E2E8F0" font-size="15" font-family="monospace">{html.escape(s["label"]):<0}</text>'
            f'<text x="330" y="{y}" fill="#94A3B8" font-size="14" font-family="monospace">{html.escape(s["sha"])}  {html.escape(ago(s["last_date"]))}</text>'
            f'<text x="640" y="{y}" fill="#94A3B8" font-size="14" font-family="monospace">CI {html.escape(s["ci"])}</text>'
            f'<text x="975" y="{y}" fill="{color}" font-size="14" font-family="monospace" text-anchor="end">{html.escape(sig)}</text>'
        )
        y += 36

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="470" viewBox="0 0 1200 470">
<rect width="1200" height="470" rx="18" fill="#0D1117"/>
<rect x="1" y="1" width="1198" height="468" rx="17" fill="none" stroke="#273449"/>
<text x="36" y="50" fill="#F8FAFC" font-size="24" font-weight="700" font-family="monospace">JOE // COMMAND V3</text>
<text x="36" y="78" fill="#67E8F9" font-size="14" font-family="monospace">LIVE MISSION CONTROL • PUBLIC TELEMETRY</text>
<text x="1164" y="50" text-anchor="end" fill="#94A3B8" font-size="13" font-family="monospace">{html.escape(stamp)}</text>
{''.join(card_svg)}
<text x="36" y="242" fill="#64748B" font-size="12" font-family="monospace">SYSTEM SIGNAL</text>
{''.join(repo_lines)}
<text x="36" y="447" fill="#475569" font-size="11" font-family="monospace">PUBLIC GITHUB METADATA ONLY • NO PRIVATE MISSION DATA • NO CREDENTIALS</text>
</svg>'''
    SVG_OUT.write_text(svg)


def replace_block(text: str, marker_prefix: str, name: str, block: str) -> str:
    pattern = rf"<!-- {marker_prefix}:{name}:START -->.*?<!-- {marker_prefix}:{name}:END -->"
    if not re.search(pattern, text, flags=re.S):
        raise RuntimeError(f"README marker missing: {marker_prefix}:{name}")
    return re.sub(pattern, block, text, count=1, flags=re.S)


def main() -> None:
    snaps = [snapshot(repo, label) for repo, label in REPOS]
    text = README.read_text()
    text = replace_block(text, "V23", "TELEMETRY", telemetry_block(snaps))
    text = replace_block(text, "V23", "MISSION_LOG", mission_log_block(snaps))
    text = replace_block(text, "V3", "PULSE", pulse_block(snaps))
    README.write_text(text)
    render_svg(snaps)
    print("JOE // COMMAND v3 mission control updated")


if __name__ == "__main__":
    main()
