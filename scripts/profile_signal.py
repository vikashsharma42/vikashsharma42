#!/usr/bin/env python3
"""Generate profile/activity.svg, the "Contribution signal" chart.

Bars are daily contributions for the last 182 days, the line is the trailing
7-day average. Data comes from GitHub's GraphQL API (needs GITHUB_TOKEN) or,
for offline use, from a JSON file of {"YYYY-MM-DD": count}.

    GITHUB_TOKEN=... python3 scripts/profile_signal.py --user vikashsharma42
    python3 scripts/profile_signal.py --from-json days.json --end 2026-10-10
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

WINDOW = 182
W, H = 1000, 330
X0, X1 = 74, 962          # plot area, left and right
Y_TOP, Y_BASE = 128, 282  # plot area, top and baseline

QUERY = (
    "query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){"
    "contributionsCollection(from:$from,to:$to){contributionCalendar{weeks{"
    "contributionDays{date contributionCount}}}}}}"
)


def fetch_days(login: str, token: str, start: date, end: date) -> dict[str, int]:
    payload = json.dumps({
        "query": QUERY,
        "variables": {"login": login, "from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"},
    }).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-signal",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors") or not body.get("data", {}).get("user"):
        sys.exit(f"GitHub API error: {body.get('errors') or 'user not found'}")
    weeks = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return {d["date"]: d["contributionCount"] for w in weeks for d in w["contributionDays"]}


def render(counts: list[int], dates: list[date]) -> str:
    n = len(counts)
    total = sum(counts)
    active = sum(1 for c in counts if c > 0)
    peak = max(counts) if counts else 0
    peak_day = dates[counts.index(peak)] if peak else None

    avg = [sum(counts[max(0, i - 6): i + 1]) / len(counts[max(0, i - 6): i + 1]) for i in range(n)]

    ymax = max(4, math.ceil(peak / 4) * 4)
    plot_h = Y_BASE - Y_TOP
    step = (X1 - X0) / n
    bar_w = max(2.0, step * 0.62)

    def sy(v: float) -> float:
        return Y_BASE - (v / ymax) * plot_h

    def cx(i: int) -> float:
        return X0 + step * i + step / 2

    out: list[str] = []
    add = out.append

    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">')
    add('<title id="t">Contribution signal</title>')
    add(f'<desc id="d">{total} contributions over the last {n} days on {active} active days. '
        f'Bars are daily contributions, the line is the 7-day average.</desc>')
    add('<defs>'
        '<linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#22D3EE" stop-opacity="0.38"/>'
        '<stop offset="1" stop-color="#22D3EE" stop-opacity="0.02"/></linearGradient>'
        '<style>'
        ".sans{font-family:'Segoe UI',Inter,'Helvetica Neue',Arial,sans-serif}"
        ".mono{font-family:'JetBrains Mono','SF Mono',Consolas,'Courier New',monospace}"
        '</style></defs>')
    add(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18" fill="#080C18" stroke="#1E293B"/>')

    add('<text x="44" y="58" class="sans" font-size="22" font-weight="700" fill="#F1F5F9">Contribution signal</text>')
    add(f'<text x="44" y="84" class="sans" font-size="14" fill="#7C8DB5">Last six months, line shows the 7-day average</text>')

    tiles = [
        (f"{total:,}", "contributions", 128),
        (f"{active}/{n}", "active days", 138),
        (f"{peak} on {peak_day:%d %b}" if peak_day else "none", "busiest day", 152),
    ]
    x = X1 - sum(t[2] for t in tiles) - 12 * (len(tiles) - 1)
    for value, label, w in tiles:
        add(f'<rect x="{x}" y="34" width="{w}" height="56" rx="12" fill="#0F172A" stroke="#1E293B"/>')
        add(f'<text x="{x + 16}" y="58" class="mono" font-size="15" font-weight="700" fill="#E2E8F0">{value}</text>')
        add(f'<text x="{x + 16}" y="77" class="mono" font-size="12" fill="#64748B">{label}</text>')
        x += w + 12

    for k in range(5):
        v = ymax * k / 4
        y = sy(v)
        add(f'<line x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}" stroke="#1E293B" stroke-width="1"/>')
        add(f'<text x="{X0 - 12}" y="{y + 4:.1f}" text-anchor="end" class="mono" font-size="11" fill="#64748B">{v:g}</text>')

    for i, c in enumerate(counts):
        if c <= 0:
            continue
        h = (c / ymax) * plot_h
        add(f'<rect x="{cx(i) - bar_w / 2:.2f}" y="{Y_BASE - h:.2f}" width="{bar_w:.2f}" height="{h:.2f}" rx="1" fill="#A78BFA" fill-opacity="0.45"/>')

    pts = [(cx(i), sy(a)) for i, a in enumerate(avg)]
    line = "M" + " L".join(f"{px:.2f},{py:.2f}" for px, py in pts)
    add(f'<path d="{line} L{pts[-1][0]:.2f},{Y_BASE} L{pts[0][0]:.2f},{Y_BASE} Z" fill="url(#area)"/>')
    add(f'<path d="{line}" fill="none" stroke="#22D3EE" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>')
    add(f'<circle cx="{pts[-1][0]:.2f}" cy="{pts[-1][1]:.2f}" r="5" fill="#A78BFA" stroke="#080C18" stroke-width="2"/>')

    for i, d in enumerate(dates):
        if d.day == 1:
            add(f'<text x="{cx(i):.1f}" y="{Y_BASE + 24}" text-anchor="middle" class="mono" font-size="11" fill="#64748B">{d:%b}</text>')

    add('</svg>')
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", default=os.environ.get("GITHUB_REPOSITORY_OWNER", ""))
    ap.add_argument("--out", default="profile/activity.svg")
    ap.add_argument("--end", help="last day, YYYY-MM-DD (default: today, UTC)")
    ap.add_argument("--from-json", help="read {date: count} from this file instead of the API")
    args = ap.parse_args()

    end = date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date()
    start = end - timedelta(days=WINDOW - 1)

    if args.from_json:
        days = json.loads(Path(args.from_json).read_text())
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token or not args.user:
            sys.exit("Set GITHUB_TOKEN and --user (or use --from-json).")
        days = fetch_days(args.user, token, start, end)

    dates = [start + timedelta(days=i) for i in range(WINDOW)]
    counts = [int(days.get(d.isoformat(), 0)) for d in dates]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(counts, dates), encoding="utf-8")
    print(f"wrote {out} ({sum(counts)} contributions, {sum(1 for c in counts if c)} active days)")


if __name__ == "__main__":
    main()