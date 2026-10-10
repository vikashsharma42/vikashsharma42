#!/usr/bin/env python3
"""Generate the "Signal" section of a profile README as self-hosted SVGs.

Writes into --out-dir (default: profile/):
  activity.svg   daily contributions for the last 182 days + 7-day average line
  streak.svg     total contributions, current streak, longest streak (last 12 months)
  stats.svg      commits, PRs, issues, reviews, repos, stars, followers
  top-langs.svg  language share across your public, non-fork repos

Live data comes from GitHub's GraphQL API (set GITHUB_TOKEN). For offline use,
pass --from-json with {"days": {"YYYY-MM-DD": n}, "stats": {...}, "langs": {...}};
a card is only written when its data is present.

    GITHUB_TOKEN=... python3 scripts/profile_signal.py --user vikashsharma42
    python3 scripts/profile_signal.py --from-json data.json --end 2026-10-10
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

# ── orange theme ────────────────────────────────────────────────────────────
BG, BORDER, TILE = "#0C0A09", "#292524", "#1C1917"
TEXT, MUTED, DIM = "#FAFAF9", "#A8A29E", "#78716C"
ACC, ACC2, ACC3, AMBER = "#F97316", "#FB923C", "#FDBA74", "#FBBF24"
LANG_COLORS = ["#F97316", "#FBBF24", "#FB7185", "#FDBA74", "#EA580C", "#FDE68A", "#B45309"]

STYLE = (
    "<style>"
    ".sans{font-family:'Segoe UI',Inter,'Helvetica Neue',Arial,sans-serif}"
    ".mono{font-family:'JetBrains Mono','SF Mono',Consolas,'Courier New',monospace}"
    "</style>"
)

WINDOW = 182          # activity chart, days
YEAR = 365            # streak / stats window, days
CARD_W, CARD_H = 490, 262


# ── data ────────────────────────────────────────────────────────────────────
QUERY = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    followers{totalCount}
    repositories(ownerAffiliations:OWNER,privacy:PUBLIC,isFork:false,first:100){
      totalCount
      nodes{stargazerCount languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}}
    }
    contributionsCollection(from:$from,to:$to){
      totalCommitContributions totalPullRequestContributions
      totalIssueContributions totalPullRequestReviewContributions
      contributionCalendar{weeks{contributionDays{date contributionCount}}}
    }
  }
}"""


def fetch(login: str, token: str, start: date, end: date) -> dict:
    payload = json.dumps({
        "query": QUERY,
        "variables": {"login": login, "from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"},
    }).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-signal"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    user = (body.get("data") or {}).get("user")
    if body.get("errors") or not user:
        sys.exit(f"GitHub API error: {body.get('errors') or 'user not found'}")

    cc = user["contributionsCollection"]
    days = {d["date"]: d["contributionCount"]
            for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]}
    repos = user["repositories"]
    langs: dict[str, int] = {}
    for r in repos["nodes"]:
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    stats = {
        "commits": cc["totalCommitContributions"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "reviews": cc["totalPullRequestReviewContributions"],
        "repos": repos["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos["nodes"]),
        "followers": user["followers"]["totalCount"],
    }
    return {"days": days, "stats": stats, "langs": langs}


# ── helpers ─────────────────────────────────────────────────────────────────
def head(w: int, h: int, tid: str, title: str, desc: str, extra_defs: str = "") -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">',
        f"<title id=\"t\">{escape(title)}</title><desc id=\"d\">{escape(desc)}</desc>",
        f"<defs>{extra_defs}{STYLE}</defs>",
        f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="18" fill="{BG}" stroke="{BORDER}"/>',
    ]


def short(d: date) -> str:
    return f"{d:%b} {d.day}"


def series(days: dict[str, int], end: date, n: int) -> tuple[list[date], list[int]]:
    dates = [end - timedelta(days=n - 1 - i) for i in range(n)]
    return dates, [int(days.get(d.isoformat(), 0)) for d in dates]


# ── activity.svg ────────────────────────────────────────────────────────────
def render_activity(dates: list[date], counts: list[int]) -> str:
    W, H = 1000, 330
    X0, X1, Y_TOP, Y_BASE = 74, 962, 128, 282
    n, total = len(counts), sum(counts)
    active = sum(1 for c in counts if c > 0)
    peak = max(counts)
    peak_day = dates[counts.index(peak)] if peak else None
    avg = [sum(counts[max(0, i - 6): i + 1]) / len(counts[max(0, i - 6): i + 1]) for i in range(n)]

    ymax = max(4, math.ceil(peak / 4) * 4)
    plot_h, step = Y_BASE - Y_TOP, (X1 - X0) / n
    bar_w = max(2.0, step * 0.62)
    sy = lambda v: Y_BASE - (v / ymax) * plot_h
    cx = lambda i: X0 + step * i + step / 2

    area = (f'<linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{ACC2}" stop-opacity="0.38"/>'
            f'<stop offset="1" stop-color="{ACC2}" stop-opacity="0.02"/></linearGradient>')
    o = head(W, H, "activity", "Contribution signal",
             f"{total} contributions over the last {n} days on {active} active days.", area)
    o.append(f'<text x="44" y="58" class="sans" font-size="22" font-weight="700" fill="{TEXT}">Contribution signal</text>')
    o.append(f'<text x="44" y="84" class="sans" font-size="14" fill="{MUTED}">Last six months, line shows the 7-day average</text>')

    tiles = [(f"{total:,}", "contributions", 128), (f"{active}/{n}", "active days", 138),
             (f"{peak} on {peak_day:%d %b}" if peak_day else "none", "busiest day", 152)]
    x = X1 - sum(t[2] for t in tiles) - 12 * (len(tiles) - 1)
    for value, label, w in tiles:
        o.append(f'<rect x="{x}" y="34" width="{w}" height="56" rx="12" fill="{TILE}" stroke="{BORDER}"/>')
        o.append(f'<text x="{x + 16}" y="58" class="mono" font-size="15" font-weight="700" fill="{TEXT}">{value}</text>')
        o.append(f'<text x="{x + 16}" y="77" class="mono" font-size="12" fill="{DIM}">{label}</text>')
        x += w + 12

    for k in range(5):
        v = ymax * k / 4
        y = sy(v)
        o.append(f'<line x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}" stroke="{BORDER}"/>')
        o.append(f'<text x="{X0 - 12}" y="{y + 4:.1f}" text-anchor="end" class="mono" font-size="11" fill="{DIM}">{v:g}</text>')

    for i, c in enumerate(counts):
        if c > 0:
            h = c / ymax * plot_h
            o.append(f'<rect x="{cx(i) - bar_w / 2:.2f}" y="{Y_BASE - h:.2f}" width="{bar_w:.2f}" height="{h:.2f}" rx="1" fill="{ACC}" fill-opacity="0.5"/>')

    pts = [(cx(i), sy(a)) for i, a in enumerate(avg)]
    line = "M" + " L".join(f"{px:.2f},{py:.2f}" for px, py in pts)
    o.append(f'<path d="{line} L{pts[-1][0]:.2f},{Y_BASE} L{pts[0][0]:.2f},{Y_BASE} Z" fill="url(#area)"/>')
    o.append(f'<path d="{line}" fill="none" stroke="{ACC3}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>')
    o.append(f'<circle cx="{pts[-1][0]:.2f}" cy="{pts[-1][1]:.2f}" r="5" fill="{AMBER}" stroke="{BG}" stroke-width="2"/>')
    for i, d in enumerate(dates):
        if d.day == 1:
            o.append(f'<text x="{cx(i):.1f}" y="{Y_BASE + 24}" text-anchor="middle" class="mono" font-size="11" fill="{DIM}">{d:%b}</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ── streak.svg ──────────────────────────────────────────────────────────────
def streaks(dates: list[date], counts: list[int]) -> dict:
    cur_end = len(counts) - 1
    if counts[cur_end] == 0:          # today may not have a contribution yet
        cur_end -= 1
    cur, i = 0, cur_end
    while i >= 0 and counts[i] > 0:
        cur, i = cur + 1, i - 1
    cur_range = (dates[i + 1], dates[cur_end]) if cur else None

    best, best_range, run, run_start = 0, None, 0, 0
    for j, c in enumerate(counts):
        if c > 0:
            if run == 0:
                run_start = j
            run += 1
            if run > best:
                best, best_range = run, (dates[run_start], dates[j])
        else:
            run = 0
    return {"cur": cur, "cur_range": cur_range, "best": best, "best_range": best_range, "total": sum(counts)}


def render_streak(dates: list[date], counts: list[int]) -> str:
    W, H = 1000, 190
    s = streaks(dates, counts)
    rng = lambda r: f"{short(r[0])} – {short(r[1])}" if r else "no active streak"
    o = head(W, H, "streak", "Contribution streak",
             f"{s['total']} contributions in the last 12 months, current streak {s['cur']} days, longest {s['best']} days.")
    cols = [(W * 1 / 6, f"{s['total']:,}", "Total contributions", "last 12 months"),
            (W * 3 / 6, str(s["cur"]), "Current streak", rng(s["cur_range"])),
            (W * 5 / 6, str(s["best"]), "Longest streak", rng(s["best_range"]))]
    for k, (x, value, label, sub) in enumerate(cols):
        if k == 1:
            r = 52
            circ = 2 * math.pi * r
            o.append(f'<circle cx="{x:.0f}" cy="82" r="{r}" fill="none" stroke="{BORDER}" stroke-width="7"/>')
            o.append(f'<circle cx="{x:.0f}" cy="82" r="{r}" fill="none" stroke="{ACC2}" stroke-width="7" stroke-linecap="round" '
                     f'stroke-dasharray="{circ * 0.82:.1f} {circ:.1f}" transform="rotate(-90 {x:.0f} 82)"/>')
            o.append(f'<text x="{x:.0f}" y="94" text-anchor="middle" class="sans" font-size="38" font-weight="800" fill="{TEXT}">{value}</text>')
            o.append(f'<text x="{x:.0f}" y="158" text-anchor="middle" class="sans" font-size="16" font-weight="700" fill="{ACC3}">{label}</text>')
            o.append(f'<text x="{x:.0f}" y="178" text-anchor="middle" class="mono" font-size="12" fill="{DIM}">{sub}</text>')
        else:
            o.append(f'<text x="{x:.0f}" y="92" text-anchor="middle" class="sans" font-size="42" font-weight="800" fill="{TEXT}">{value}</text>')
            o.append(f'<text x="{x:.0f}" y="128" text-anchor="middle" class="sans" font-size="16" font-weight="700" fill="{ACC3}">{label}</text>')
            o.append(f'<text x="{x:.0f}" y="150" text-anchor="middle" class="mono" font-size="12" fill="{DIM}">{sub}</text>')
    for x in (W / 3, 2 * W / 3):
        o.append(f'<line x1="{x:.0f}" y1="36" x2="{x:.0f}" y2="{H - 36}" stroke="{BORDER}"/>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ── stats.svg ───────────────────────────────────────────────────────────────
def render_stats(stats: dict) -> str:
    rows = [("Commits (12 months)", stats["commits"]), ("Pull requests", stats["prs"]),
            ("Issues", stats["issues"]), ("Code reviews", stats["reviews"]),
            ("Public repositories", stats["repos"]), ("Stars earned", stats["stars"]),
            ("Followers", stats["followers"])]
    o = head(CARD_W, CARD_H, "stats", "GitHub stats", "Commits, pull requests, issues, reviews, repositories, stars and followers.")
    o.append(f'<text x="30" y="46" class="sans" font-size="20" font-weight="700" fill="{TEXT}">GitHub stats</text>')
    o.append(f'<rect x="30" y="56" width="36" height="3" rx="1.5" fill="{ACC}"/>')
    y = 92
    for label, value in rows:
        o.append(f'<circle cx="38" cy="{y - 5}" r="4" fill="{ACC}"/>')
        o.append(f'<text x="54" y="{y}" class="sans" font-size="15" fill="{MUTED}">{label}</text>')
        o.append(f'<text x="{CARD_W - 30}" y="{y}" text-anchor="end" class="mono" font-size="15" font-weight="700" fill="{TEXT}">{int(value):,}</text>')
        y += 25
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ── top-langs.svg ───────────────────────────────────────────────────────────
def render_langs(langs: dict[str, int]) -> str:
    items = sorted(langs.items(), key=lambda kv: kv[1], reverse=True)[:6]
    total = sum(v for _, v in items) or 1
    o = head(CARD_W, CARD_H, "langs", "Top languages",
             "Language share across public, non-fork repositories: " + ", ".join(f"{k} {v / total:.0%}" for k, v in items))
    o.append(f'<text x="30" y="46" class="sans" font-size="20" font-weight="700" fill="{TEXT}">Top languages</text>')
    o.append(f'<rect x="30" y="56" width="36" height="3" rx="1.5" fill="{ACC}"/>')
    bar_x, bar_w = 30, CARD_W - 60
    o.append(f'<clipPath id="bar"><rect x="{bar_x}" y="76" width="{bar_w}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">')
    x = float(bar_x)
    for k, (name, v) in enumerate(items):
        w = bar_w * v / total
        o.append(f'<rect x="{x:.1f}" y="76" width="{w + 0.5:.1f}" height="10" fill="{LANG_COLORS[k % len(LANG_COLORS)]}"/>')
        x += w
    o.append("</g>")
    y = 118
    for k, (name, v) in enumerate(items):
        o.append(f'<circle cx="38" cy="{y - 5}" r="5" fill="{LANG_COLORS[k % len(LANG_COLORS)]}"/>')
        o.append(f'<text x="54" y="{y}" class="sans" font-size="15" fill="{MUTED}">{escape(name)}</text>')
        o.append(f'<text x="{CARD_W - 30}" y="{y}" text-anchor="end" class="mono" font-size="15" font-weight="700" fill="{TEXT}">{v / total:.1%}</text>')
        y += 24
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", default=os.environ.get("GITHUB_REPOSITORY_OWNER", ""))
    ap.add_argument("--out-dir", default="profile")
    ap.add_argument("--end", help="last day, YYYY-MM-DD (default: today, UTC)")
    ap.add_argument("--from-json", help="offline data file instead of the API")
    args = ap.parse_args()

    end = date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date()

    if args.from_json:
        raw = json.loads(Path(args.from_json).read_text())
        data = raw if "days" in raw else {"days": raw}
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token or not args.user:
            sys.exit("Set GITHUB_TOKEN and --user (or use --from-json).")
        data = fetch(args.user, token, end - timedelta(days=YEAR - 1), end)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []

    y_dates, y_counts = series(data["days"], end, YEAR)
    jobs = {
        "activity.svg": lambda: render_activity(*series(data["days"], end, WINDOW)),
        "streak.svg": lambda: render_streak(y_dates, y_counts),
    }
    if data.get("stats"):
        jobs["stats.svg"] = lambda: render_stats(data["stats"])
    if data.get("langs"):
        jobs["top-langs.svg"] = lambda: render_langs(data["langs"])
    for name, make in jobs.items():
        (out / name).write_text(make(), encoding="utf-8")
        written.append(name)
    print(f"wrote {', '.join(written)} to {out}/")


if __name__ == "__main__":
    main()