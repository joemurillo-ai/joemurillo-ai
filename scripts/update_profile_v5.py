from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OWNER = "joemurillo-ai"
README = Path("README.md")
LIVE_SVG = Path("assets/live-command.svg")
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
        "User-Agent": "joe-command-profile-v5",
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
    return f"{max(0, int(delta.total_seconds() // 60))}m ago"


def clean(text: str, limit: int = 72) -> str:
    text = re.sub(r"\s+", " ", text.strip()).replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def latest_ci(repo: str) -> tuple[str, str]:
    runs = api(f"/repos/{OWNER}/{repo}/actions/runs?per_page=1") or {}
    rows = runs.get("workflow_runs") or []
    if not rows:
        return "—", "none"
    run = rows[0]
    if run.get("status") != "completed":
        status = run.get("status") or "unknown"
        return status.upper(), status
    conclusion = run.get("conclusion") or "unknown"
    return conclusion.upper(), conclusion


def count_recent(commits: list[dict], days: int) -> int:
    cutoff = now_utc() - timedelta(days=days)
    total = 0
    for commit in commits:
        dt = parse_dt(commit.get("commit", {}).get("committer", {}).get("date"))
        if dt and dt >= cutoff:
            total += 1
    return total


def snapshot(repo: str, label: str) -> dict:
    meta = api(f"/repos/{OWNER}/{repo}") or {}
    commits = api(f"/repos/{OWNER}/{repo}/commits?per_page=100") or []
    pulls = api(f"/repos/{OWNER}/{repo}/pulls?state=open&per_page=100") or []
    issues_raw = api(f"/repos/{OWNER}/{repo}/issues?state=open&per_page=100") or []
    issues = [item for item in issues_raw if "pull_request" not in item]
    last = commits[0] if commits else {}
    last_date = last.get("commit", {}).get("committer", {}).get("date")
    ci_label, ci_raw = latest_ci(repo)
    return {
        "repo": repo,
        "label": label,
        "branch": meta.get("default_branch", "—"),
        "sha": (last.get("sha") or "—")[:7],
        "last_date": last_date,
        "pulls": pulls,
        "issues": issues,
        "open_prs": len(pulls),
        "open_issues": len(issues),
        "ci": ci_label,
        "ci_raw": ci_raw,
        "commits": commits,
        "c7": count_recent(commits, 7),
        "c30": count_recent(commits, 30),
    }


def activity(s: dict) -> str:
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
    return "DORMANT"


def pressure(s: dict) -> str:
    work = s["open_prs"] + s["open_issues"]
    if work == 0:
        return "CLEAR"
    if work <= 3:
        return "LIGHT"
    return "ELEVATED"


def signal(s: dict) -> str:
    state = activity(s)
    if state == "ATTENTION":
        return "ATTENTION"
    if state == "ACTIVE" and s["ci_raw"] in {"success", "none"}:
        return "GREEN"
    if state == "WARM":
        return "AMBER"
    if state == "DORMANT":
        return "STANDBY"
    return "UNKNOWN"


def pulse_block(snaps: list[dict]) -> str:
    focus = max(snaps, key=lambda s: (s["c7"], s["c30"]))["label"] if snaps else "—"
    return "\n".join([
        "<!-- V5:PULSE:START -->",
        "```text",
        "PORTFOLIO PULSE",
        "----------------------------------------------------------------",
        f"commits_7d           {sum(s['c7'] for s in snaps)}",
        f"commits_30d          {sum(s['c30'] for s in snaps)}",
        f"active_repos_30d     {sum(1 for s in snaps if s['c30'] > 0)}/{len(snaps)}",
        f"ci_success           {sum(1 for s in snaps if s['ci_raw'] == 'success')}",
        f"attention_signals    {sum(1 for s in snaps if activity(s) == 'ATTENTION')}",
        f"open_prs             {sum(s['open_prs'] for s in snaps)}",
        f"open_issues          {sum(s['open_issues'] for s in snaps)}",
        f"focus_repo           {focus}",
        "```",
        "<!-- V5:PULSE:END -->",
    ])


def trust_block(snaps: list[dict]) -> str:
    lines = [
        "<!-- V5:TRUST:START -->",
        "| System | Activity | CI | Work pressure | Operational signal |",
        "|---|---|---|---|---|",
    ]
    for s in snaps:
        lines.append(f"| {s['label']} | {activity(s)} | {s['ci']} | {pressure(s)} | {signal(s)} |")
    lines.append("<!-- V5:TRUST:END -->")
    return "\n".join(lines)


def queue_block(snaps: list[dict]) -> str:
    work = []
    for s in snaps:
        for pr in s["pulls"]:
            work.append((pr.get("updated_at") or "", "PR", s["repo"], pr.get("number"), clean(pr.get("title", ""), 66), pr.get("html_url", "#")))
        for issue in s["issues"]:
            work.append((issue.get("updated_at") or "", "ISSUE", s["repo"], issue.get("number"), clean(issue.get("title", ""), 66), issue.get("html_url", "#")))
    work.sort(reverse=True)
    if not work:
        body = "```text\nQUEUE CLEAR — no open public PRs or issues across tracked repositories.\n```"
    else:
        rows = ["| Type | System | Work item |", "|---|---|---|"]
        for _, kind, repo, number, title, url in work[:8]:
            rows.append(f"| {kind} | `{repo}` | [#{number} {title}]({url}) |")
        body = "\n".join(rows)
    return "\n".join(["<!-- V5:QUEUE:START -->", body, "<!-- V5:QUEUE:END -->"])


def telemetry_block(snaps: list[dict]) -> str:
    rows = []
    for s in snaps:
        rows.append(
            f"| [{s['label']}](https://github.com/{OWNER}/{s['repo']}) | `{s['branch']}` | `{s['sha']}` | {ago(s['last_date'])} | "
            f"{s['c7']} | {s['c30']} | {s['open_prs']} | {s['open_issues']} | {s['ci']} | {activity(s)} |"
        )
    stamp = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join([
        "<!-- V5:TELEMETRY:START -->",
        "| System | Branch | Head | Last commit | 7d | 30d | PRs | Issues | Latest Action | Signal |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
        *rows,
        "",
        f"`telemetry_sync: {stamp}`  ",
        "`boundary: public GitHub metadata only`",
        "<!-- V5:TELEMETRY:END -->",
    ])


def mission_log_block(snaps: list[dict]) -> str:
    events = []
    for s in snaps:
        for commit in s["commits"][:12]:
            c = commit.get("commit", {})
            date = c.get("committer", {}).get("date")
            if date:
                events.append((date, s["repo"], (commit.get("sha") or "")[:7], clean(c.get("message", "").splitlines()[0]), commit.get("html_url", "#")))
    events.sort(reverse=True)
    lines = ["<!-- V5:MISSION_LOG:START -->", "| UTC | System | Mission event | Commit |", "|---|---|---|---|"]
    for date, repo, sha, message, url in events[:12]:
        dt = parse_dt(date)
        stamp = dt.strftime("%Y-%m-%d %H:%M") if dt else "—"
        lines.append(f"| {stamp} | `{repo}` | {message} | [`{sha}`]({url}) |")
    lines.append("<!-- V5:MISSION_LOG:END -->")
    return "\n".join(lines)


def replace_block(text: str, name: str, block: str) -> str:
    pattern = rf"<!-- V5:{name}:START -->.*?<!-- V5:{name}:END -->"
    if not re.search(pattern, text, flags=re.S):
        raise RuntimeError(f"README marker missing: V5:{name}")
    return re.sub(pattern, block, text, count=1, flags=re.S)


def color(sig: str) -> str:
    return {"GREEN": "#F8FAFC", "AMBER": "#B8B8B8", "ATTENTION": "#FFFFFF", "STANDBY": "#777777", "UNKNOWN": "#999999"}.get(sig, "#999999")


def render_live_svg(snaps: list[dict]) -> None:
    focus = max(snaps, key=lambda s: (s["c7"], s["c30"]))["label"] if snaps else "—"
    stamp = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    metrics = [
        ("7D COMMITS", sum(s["c7"] for s in snaps)),
        ("30D COMMITS", sum(s["c30"] for s in snaps)),
        ("ACTIVE REPOS", f"{sum(1 for s in snaps if s['c30'] > 0)}/{len(snaps)}"),
        ("CI PASSING", sum(1 for s in snaps if s["ci_raw"] == "success")),
        ("ATTENTION", sum(1 for s in snaps if activity(s) == "ATTENTION")),
        ("OPEN WORK", sum(s["open_prs"] + s["open_issues"] for s in snaps)),
    ]
    cards = []
    for i, (label, value) in enumerate(metrics):
        x = 32 + i * 190
        cards.append(f'<rect x="{x}" y="116" width="170" height="88" rx="10" fill="#101010" stroke="#343434"/>'
                     f'<text x="{x+14}" y="143" fill="#A7A7A7" font-size="12" font-family="monospace">{html.escape(str(label))}</text>'
                     f'<text x="{x+14}" y="182" fill="#FFFFFF" font-size="30" font-weight="700" font-family="monospace">{html.escape(str(value))}</text>')
    lines = []
    y = 252
    for s in snaps:
        sig = signal(s)
        c = color(sig)
        lines.append(f'<circle cx="48" cy="{y-5}" r="5" fill="{c}"/>'
                     f'<text x="64" y="{y}" fill="#E7E7E7" font-size="14" font-family="monospace">{html.escape(s["label"])}</text>'
                     f'<text x="340" y="{y}" fill="#8A8A8A" font-size="13" font-family="monospace">{html.escape(s["sha"])} • {html.escape(ago(s["last_date"]))}</text>'
                     f'<text x="660" y="{y}" fill="#8A8A8A" font-size="13" font-family="monospace">CI {html.escape(s["ci"])} • 7D {s["c7"]}</text>'
                     f'<text x="1140" y="{y}" fill="{c}" font-size="13" font-family="monospace" text-anchor="end">{html.escape(sig)}</text>')
        y += 34
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="470" viewBox="0 0 1200 470">
<rect width="1200" height="470" rx="18" fill="#080808"/>
<rect x="1" y="1" width="1198" height="468" rx="17" fill="none" stroke="#2D2D2D"/>
<text x="32" y="48" fill="#FFFFFF" font-size="24" font-weight="700" font-family="monospace">JOE // COMMAND V5</text>
<text x="32" y="76" fill="#B7B7B7" font-size="14" font-family="monospace">IDENTITY + PORTFOLIO OPERATING SYSTEM • LIVE COMMAND DECK</text>
<text x="1168" y="48" text-anchor="end" fill="#777777" font-size="12" font-family="monospace">{html.escape(stamp)}</text>
<text x="1168" y="76" text-anchor="end" fill="#D0D0D0" font-size="12" font-family="monospace">FOCUS: {html.escape(focus)}</text>
{''.join(cards)}
<text x="32" y="226" fill="#666666" font-size="11" font-family="monospace">SYSTEM / SIGNAL</text>
{''.join(lines)}
<text x="32" y="448" fill="#555555" font-size="11" font-family="monospace">PUBLIC GITHUB METADATA ONLY • NO PRIVATE MISSION DATA • NO CREDENTIALS</text>
</svg>'''
    LIVE_SVG.write_text(svg)


def main() -> None:
    snaps = [snapshot(repo, label) for repo, label in REPOS]
    text = README.read_text()
    for name, block in [
        ("PULSE", pulse_block(snaps)),
        ("TRUST", trust_block(snaps)),
        ("QUEUE", queue_block(snaps)),
        ("TELEMETRY", telemetry_block(snaps)),
        ("MISSION_LOG", mission_log_block(snaps)),
    ]:
        text = replace_block(text, name, block)
    README.write_text(text)
    render_live_svg(snaps)
    print("JOE // COMMAND V5 identity operating system updated")


if __name__ == "__main__":
    main()
