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
GRAPH_SVG = Path("assets/portfolio-graph.svg")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

REPOS = [
    ("aris", "ARIS"),
    ("xoris-ai", "XORIS"),
    ("pcap-triage-pipeline", "PCAP TRIAGE"),
    ("azure-ai-security-briefing-agent", "SECURITY BRIEFING"),
    ("humanexe", "HUMAN.EXE"),
]

GREEN = "#39FF88"
CYAN = "#6EE7F9"
WHITE = "#F8FAFC"
MUTED = "#8B949E"
PANEL = "#0D1117"
CARD = "#10161D"
BORDER = "#1F6F5B"
RED = "#FF5C5C"
AMBER = "#F6C85F"


def api(path: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "joe-command-profile-v5-2",
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


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ago(value: str | None) -> str:
    dt = parse_dt(value)
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
    runs = api(f"/repos/{OWNER}/{repo}/actions/runs?per_page=1") or {}
    rows = runs.get("workflow_runs") or []
    if not rows:
        return "—", "none"
    run = rows[0]
    status = run.get("status") or "unknown"
    if status != "completed":
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
    latest = commits[0] if commits else {}
    latest_date = latest.get("commit", {}).get("committer", {}).get("date")
    ci_label, ci_raw = latest_ci(repo)
    return {
        "repo": repo,
        "label": label,
        "branch": meta.get("default_branch", "—"),
        "sha": (latest.get("sha") or "—")[:7],
        "last_date": latest_date,
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


def work_pressure(s: dict) -> str:
    total = s["open_prs"] + s["open_issues"]
    if total == 0:
        return "CLEAR"
    if total <= 3:
        return "LIGHT"
    return "ELEVATED"


def op_signal(s: dict) -> str:
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
    c7 = sum(s["c7"] for s in snaps)
    c30 = sum(s["c30"] for s in snaps)
    active30 = sum(1 for s in snaps if s["c30"] > 0)
    passing = sum(1 for s in snaps if s["ci_raw"] == "success")
    attention = sum(1 for s in snaps if activity(s) == "ATTENTION")
    prs = sum(s["open_prs"] for s in snaps)
    issues = sum(s["open_issues"] for s in snaps)
    focus = max(snaps, key=lambda s: (s["c7"], s["c30"]))["label"] if snaps else "—"
    return "\n".join([
        "<!-- V5:PULSE:START -->",
        "```text",
        "PORTFOLIO PULSE",
        "----------------------------------------------------------------",
        f"commits_7d           {c7}",
        f"commits_30d          {c30}",
        f"active_repos_30d     {active30}/{len(snaps)}",
        f"ci_success           {passing}",
        f"attention_signals    {attention}",
        f"open_prs             {prs}",
        f"open_issues          {issues}",
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
        lines.append(f"| {s['label']} | {activity(s)} | {s['ci']} | {work_pressure(s)} | {op_signal(s)} |")
    lines.append("<!-- V5:TRUST:END -->")
    return "\n".join(lines)


def queue_block(snaps: list[dict]) -> str:
    work = []
    for s in snaps:
        for pr in s["pulls"]:
            work.append((pr.get("updated_at") or "", "PR", s["repo"], pr.get("number"), clean(pr.get("title", ""), 62)))
        for issue in s["issues"]:
            work.append((issue.get("updated_at") or "", "ISSUE", s["repo"], issue.get("number"), clean(issue.get("title", ""), 62)))
    work.sort(reverse=True)
    if not work:
        body = "```text\nQUEUE CLEAR — no open public PRs or issues across tracked repositories.\n```"
    else:
        rows = ["| Type | System | Work item |", "|---|---|---|"]
        for _, kind, repo, number, title in work[:8]:
            rows.append(f"| {kind} | `{repo}` | #{number} {title} |")
        body = "\n".join(rows)
    return "\n".join(["<!-- V5:QUEUE:START -->", body, "<!-- V5:QUEUE:END -->"])


def telemetry_block(snaps: list[dict]) -> str:
    rows = []
    for s in snaps:
        rows.append(
            f"| {s['label']} | `{s['branch']}` | `{s['sha']}` | {ago(s['last_date'])} | {s['c7']} | {s['c30']} | "
            f"{s['open_prs']} | {s['open_issues']} | {s['ci']} | {activity(s)} |"
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
                events.append((date, s["repo"], (commit.get("sha") or "")[:7], clean(c.get("message", "").splitlines()[0])))
    events.sort(reverse=True)
    lines = [
        "<!-- V5:MISSION_LOG:START -->",
        "| UTC | System | Mission event | Commit |",
        "|---|---|---|---|",
    ]
    for date, repo, sha, message in events[:12]:
        dt = parse_dt(date)
        stamp = dt.strftime("%Y-%m-%d %H:%M") if dt else "—"
        lines.append(f"| {stamp} | `{repo}` | {message} | `{sha}` |")
    lines.append("<!-- V5:MISSION_LOG:END -->")
    return "\n".join(lines)


def svg_color(signal: str) -> str:
    return {"GREEN": GREEN, "AMBER": AMBER, "ATTENTION": RED, "STANDBY": MUTED, "UNKNOWN": MUTED}.get(signal, MUTED)


def render_live_svg(snaps: list[dict]) -> None:
    c7 = sum(s["c7"] for s in snaps)
    c30 = sum(s["c30"] for s in snaps)
    active30 = sum(1 for s in snaps if s["c30"] > 0)
    passing = sum(1 for s in snaps if s["ci_raw"] == "success")
    attention = sum(1 for s in snaps if activity(s) == "ATTENTION")
    work = sum(s["open_prs"] + s["open_issues"] for s in snaps)
    focus = max(snaps, key=lambda s: (s["c7"], s["c30"]))["label"] if snaps else "—"
    stamp = now_utc().strftime("%Y-%m-%d %H:%M UTC")

    cards = [("7D COMMITS", str(c7)), ("30D COMMITS", str(c30)), ("ACTIVE REPOS", f"{active30}/{len(snaps)}"), ("CI PASSING", str(passing)), ("ATTENTION", str(attention)), ("OPEN WORK", str(work))]
    card_svg = []
    for i, (label, value) in enumerate(cards):
        x = 32 + i * 190
        card_svg.append(
            f'<rect x="{x}" y="116" width="170" height="88" rx="12" fill="{CARD}" stroke="{BORDER}"/>'
            f'<text x="{x+14}" y="143" fill="{CYAN}" font-size="12" font-family="monospace">{html.escape(label)}</text>'
            f'<text x="{x+14}" y="182" fill="{WHITE}" font-size="30" font-weight="700" font-family="monospace">{html.escape(value)}</text>'
        )

    repo_lines = []
    y = 252
    for s in snaps:
        signal = op_signal(s)
        color = svg_color(signal)
        repo_lines.append(
            f'<circle cx="48" cy="{y-5}" r="5" fill="{color}"/>'
            f'<text x="64" y="{y}" fill="{WHITE}" font-size="14" font-family="monospace">{html.escape(s["label"])}</text>'
            f'<text x="340" y="{y}" fill="{MUTED}" font-size="13" font-family="monospace">{html.escape(s["sha"])} • {html.escape(ago(s["last_date"]))}</text>'
            f'<text x="660" y="{y}" fill="{MUTED}" font-size="13" font-family="monospace">CI {html.escape(s["ci"])} • 7D {s["c7"]}</text>'
            f'<text x="1140" y="{y}" fill="{color}" font-size="13" font-family="monospace" text-anchor="end">{html.escape(signal)}</text>'
        )
        y += 34

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="470" viewBox="0 0 1200 470">
<rect width="1200" height="470" rx="18" fill="{PANEL}"/>
<rect x="1" y="1" width="1198" height="468" rx="17" fill="none" stroke="{BORDER}"/>
<text x="32" y="48" fill="{GREEN}" font-size="24" font-weight="700" font-family="monospace">JOE // COMMAND V5.2</text>
<text x="32" y="76" fill="{CYAN}" font-size="14" font-family="monospace">TERMINAL IDENTITY • LIVE COMMAND DECK</text>
<text x="1168" y="48" text-anchor="end" fill="{MUTED}" font-size="12" font-family="monospace">{html.escape(stamp)}</text>
<text x="1168" y="76" text-anchor="end" fill="{GREEN}" font-size="12" font-family="monospace">FOCUS: {html.escape(focus)}</text>
{''.join(card_svg)}
<text x="32" y="226" fill="{MUTED}" font-size="11" font-family="monospace">SYSTEM / SIGNAL</text>
{''.join(repo_lines)}
<text x="32" y="448" fill="{MUTED}" font-size="11" font-family="monospace">PUBLIC GITHUB METADATA ONLY • NO PRIVATE MISSION DATA • NO CREDENTIALS</text>
</svg>'''
    LIVE_SVG.write_text(svg)


def render_graph_svg(snaps: list[dict]) -> None:
    status = {s["repo"]: op_signal(s) for s in snaps}
    aris = svg_color(status.get("aris", "UNKNOWN"))
    xoris = svg_color(status.get("xoris-ai", "UNKNOWN"))
    graph = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="390" viewBox="0 0 1200 390">
<rect width="1200" height="390" rx="18" fill="{PANEL}"/>
<rect x="1" y="1" width="1198" height="388" rx="17" fill="none" stroke="{BORDER}"/>
<text x="36" y="46" fill="{GREEN}" font-size="22" font-weight="700" font-family="monospace">INTELLIGENCE SYSTEM GRAPH</text>
<text x="36" y="72" fill="{MUTED}" font-size="12" font-family="monospace">authority → governance → reasoning → physical verification → outcome intelligence</text>
<rect x="64" y="142" width="150" height="70" rx="12" fill="{CARD}" stroke="{GREEN}"/><text x="139" y="170" text-anchor="middle" fill="{WHITE}" font-size="18" font-weight="700" font-family="monospace">JOE</text><text x="139" y="192" text-anchor="middle" fill="{MUTED}" font-size="11" font-family="monospace">HUMAN AUTHORITY</text>
<path d="M214 177 H302" stroke="{BORDER}" stroke-width="2"/><polygon points="302,177 292,171 292,183" fill="{BORDER}"/>
<rect x="302" y="142" width="168" height="70" rx="12" fill="{CARD}" stroke="{xoris}"/><text x="386" y="170" text-anchor="middle" fill="{WHITE}" font-size="18" font-weight="700" font-family="monospace">XORIS</text><text x="386" y="192" text-anchor="middle" fill="{MUTED}" font-size="11" font-family="monospace">CONTROL / GOVERN</text>
<path d="M470 177 H558" stroke="{BORDER}" stroke-width="2"/><polygon points="558,177 548,171 548,183" fill="{BORDER}"/>
<rect x="558" y="142" width="168" height="70" rx="12" fill="{CARD}" stroke="{aris}"/><text x="642" y="170" text-anchor="middle" fill="{WHITE}" font-size="18" font-weight="700" font-family="monospace">ARIS</text><text x="642" y="192" text-anchor="middle" fill="{MUTED}" font-size="11" font-family="monospace">REASON / DECIDE</text>
<path d="M726 177 H814" stroke="{BORDER}" stroke-width="2"/><polygon points="814,177 804,171 804,183" fill="{BORDER}"/>
<rect x="814" y="142" width="150" height="70" rx="12" fill="{CARD}" stroke="{CYAN}"/><text x="889" y="170" text-anchor="middle" fill="{WHITE}" font-size="18" font-weight="700" font-family="monospace">CENTRA</text><text x="889" y="192" text-anchor="middle" fill="{MUTED}" font-size="11" font-family="monospace">SENSE / VERIFY</text>
<path d="M964 177 H1040" stroke="{BORDER}" stroke-width="2"/><polygon points="1040,177 1030,171 1030,183" fill="{BORDER}"/>
<rect x="1040" y="132" width="116" height="90" rx="12" fill="{CARD}" stroke="{GREEN}"/><text x="1098" y="162" text-anchor="middle" fill="{WHITE}" font-size="13" font-weight="700" font-family="monospace">RISK</text><text x="1098" y="181" text-anchor="middle" fill="{WHITE}" font-size="13" font-weight="700" font-family="monospace">GRAPH</text><text x="1098" y="203" text-anchor="middle" fill="{MUTED}" font-size="10" font-family="monospace">OUTCOMES</text>
<text x="642" y="278" text-anchor="middle" fill="{GREEN}" font-size="12" font-family="monospace">ATLAS • truth</text><text x="642" y="300" text-anchor="middle" fill="{CYAN}" font-size="12" font-family="monospace">PRAXIS • planning</text><text x="642" y="322" text-anchor="middle" fill="{AMBER}" font-size="12" font-family="monospace">SENTINEL • challenge</text>
<text x="36" y="365" fill="{MUTED}" font-size="11" font-family="monospace">LIVE PUBLIC SIGNALS FROM TRACKED GITHUB REPOSITORIES • PLANNED SYSTEMS ARE NOT SHOWN AS DEPLOYED</text>
</svg>'''
    GRAPH_SVG.write_text(graph)


def replace_block(text: str, name: str, block: str) -> str:
    pattern = rf"<!-- V5:{name}:START -->.*?<!-- V5:{name}:END -->"
    if not re.search(pattern, text, flags=re.S):
        raise RuntimeError(f"README marker missing: V5:{name}")
    return re.sub(pattern, block, text, count=1, flags=re.S)


def main() -> None:
    snaps = [snapshot(repo, label) for repo, label in REPOS]
    text = README.read_text()
    text = replace_block(text, "PULSE", pulse_block(snaps))
    text = replace_block(text, "TRUST", trust_block(snaps))
    text = replace_block(text, "QUEUE", queue_block(snaps))
    text = replace_block(text, "TELEMETRY", telemetry_block(snaps))
    text = replace_block(text, "MISSION_LOG", mission_log_block(snaps))
    README.write_text(text)
    render_live_svg(snaps)
    render_graph_svg(snaps)
    print("JOE // COMMAND V5.2 terminal-green profile updated")


if __name__ == "__main__":
    main()
