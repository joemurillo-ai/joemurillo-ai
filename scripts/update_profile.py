from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OWNER = "joemurillo-ai"
README = Path("README.md")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

REPOS = [
    ("aris", "ARIS"),
    ("xoris-ai", "XORIS"),
    ("pcap-triage-pipeline", "PCAP TRIAGE"),
    ("azure-ai-security-briefing-agent", "SECURITY BRIEFING"),
    ("humanexe", "HUMAN.EXE"),
]
MISSION_REPOS = ["aris", "xoris-ai", "humanexe"]


def api(path: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "joe-command-profile-v2.3",
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


def ago(iso: str | None) -> str:
    if not iso:
        return "n/a"
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - dt
    if delta.days >= 1:
        return f"{delta.days}d ago"
    hours = max(0, int(delta.total_seconds() // 3600))
    if hours >= 1:
        return f"{hours}h ago"
    mins = max(0, int(delta.total_seconds() // 60))
    return f"{mins}m ago"


def clean(text: str, limit: int = 64) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    text = text.replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def latest_ci(repo: str) -> str:
    runs = api(f"/repos/{OWNER}/{repo}/actions/runs?per_page=1")
    if not runs or not runs.get("workflow_runs"):
        return "—"
    run = runs["workflow_runs"][0]
    if run.get("status") != "completed":
        return run.get("status", "—").upper()
    conclusion = run.get("conclusion") or "—"
    return conclusion.upper()


def repo_row(repo: str, label: str) -> str:
    meta = api(f"/repos/{OWNER}/{repo}") or {}
    commits = api(f"/repos/{OWNER}/{repo}/commits?per_page=1") or []
    pulls = api(f"/repos/{OWNER}/{repo}/pulls?state=open&per_page=100") or []
    issues = api(f"/repos/{OWNER}/{repo}/issues?state=open&per_page=100") or []
    real_issues = [i for i in issues if "pull_request" not in i]
    last = commits[0] if commits else {}
    last_date = last.get("commit", {}).get("committer", {}).get("date")
    sha = (last.get("sha") or "—")[:7]
    branch = meta.get("default_branch", "—")
    ci = latest_ci(repo)
    return (
        f"| [{label}](https://github.com/{OWNER}/{repo}) "
        f"| `{branch}` | `{sha}` | {ago(last_date)} | {len(pulls)} | {len(real_issues)} | {ci} |"
    )


def telemetry_block() -> str:
    rows = [repo_row(repo, label) for repo, label in REPOS]
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join([
        "<!-- V23:TELEMETRY:START -->",
        "| System | Branch | Head | Last commit | Open PRs | Open issues | Latest Action |",
        "|---|---|---:|---:|---:|---:|---|",
        *rows,
        "",
        f"`telemetry_sync: {synced}`  ",
        "`boundary: public GitHub metadata only`",
        "<!-- V23:TELEMETRY:END -->",
    ])


def mission_log_block() -> str:
    events = []
    for repo in MISSION_REPOS:
        commits = api(f"/repos/{OWNER}/{repo}/commits?per_page=5") or []
        for commit in commits:
            c = commit.get("commit", {})
            date = c.get("committer", {}).get("date")
            if not date:
                continue
            events.append({
                "date": date,
                "repo": repo,
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
    for event in events[:10]:
        dt = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
        stamp = dt.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"| {stamp} | `{event['repo']}` | {event['message']} | "
            f"[`{event['sha']}`]({event['url']}) |"
        )
    lines.append("<!-- V23:MISSION_LOG:END -->")
    return "\n".join(lines)


def replace_block(text: str, name: str, block: str) -> str:
    pattern = rf"<!-- V23:{name}:START -->.*?<!-- V23:{name}:END -->"
    if not re.search(pattern, text, flags=re.S):
        raise RuntimeError(f"README marker missing: {name}")
    return re.sub(pattern, block, text, count=1, flags=re.S)


def main() -> None:
    text = README.read_text()
    text = replace_block(text, "TELEMETRY", telemetry_block())
    text = replace_block(text, "MISSION_LOG", mission_log_block())
    README.write_text(text)
    print("JOE // COMMAND v2.3 telemetry updated")


if __name__ == "__main__":
    main()
