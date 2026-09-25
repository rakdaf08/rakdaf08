"""Render assets/stats.svg from the GitHub GraphQL API.

Runs daily in .github/workflows/stats.yml with the built-in GITHUB_TOKEN,
so only public data is used. Locally: GITHUB_TOKEN=$(gh auth token) python scripts/stats.py
"""

import json
import os
import urllib.request
from datetime import date, timedelta
from pathlib import Path

LOGIN = "rakdaf08"
# Notebook outputs dwarf real source size, so they would drown every other language
EXCLUDED_LANGUAGES = {"Jupyter Notebook"}
OUT = Path(__file__).resolve().parent.parent / "assets" / "stats.svg"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={
            "Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as res:
        payload = json.load(res)
    if "errors" in payload:
        raise SystemExit(payload["errors"])
    return payload["data"]["user"]


def streaks(days):
    counts = {d["date"]: d["contributionCount"] for d in days}
    ordered = sorted(counts)

    longest = run = 0
    for day in ordered:
        run = run + 1 if counts[day] else 0
        longest = max(longest, run)

    # A streak is still alive if today has nothing yet but yesterday does
    current = 0
    cursor = date.fromisoformat(ordered[-1])
    if not counts.get(cursor.isoformat()):
        cursor -= timedelta(days=1)
    while counts.get(cursor.isoformat()):
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def languages(repos, top=6):
    totals, colors = {}, {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in EXCLUDED_LANGUAGES:
                continue
            totals[name] = totals.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or "#8b949e"
    grand = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return [(name, size / grand * 100, colors[name]) for name, size in ranked]


def render(user):
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [d for w in calendar["weeks"] for d in w["contributionDays"]]
    current, longest = streaks(days)
    repos = user["repositories"]["nodes"]
    langs = languages(repos)

    metrics = [
        (f"{calendar['totalContributions']:,}", "contributions, last 12 months"),
        (f"{current}", "day current streak"),
        (f"{longest}", "day longest streak"),
        (f"{user['repositories']['totalCount']}", "public repositories"),
    ]

    width, pad = 800, 0
    col = (width - 2 * pad) / len(metrics)
    parts = []
    for i, (value, label) in enumerate(metrics):
        x = pad + i * col
        parts.append(f'<text x="{x:.0f}" y="40" class="value">{value}</text>')
        parts.append(f'<text x="{x:.0f}" y="64" class="label">{label}</text>')

    # Language bar: segments scaled to the shown languages, legend underneath
    bar_y, bar_w = 112, width - 2 * pad
    shown = sum(p for _, p, _ in langs) or 1
    x = pad
    parts.append(f'<text x="{pad}" y="{bar_y - 14}" class="label">Most used languages in public repos</text>')
    parts.append(f'<clipPath id="bar"><rect x="{pad}" y="{bar_y}" width="{bar_w}" height="8" rx="4"/></clipPath>')
    parts.append('<g clip-path="url(#bar)">')
    for name, pct, color in langs:
        w = bar_w * pct / shown
        parts.append(f'<rect x="{x:.1f}" y="{bar_y}" width="{w:.1f}" height="8" fill="{color}"/>')
        x += w
    parts.append("</g>")

    lx, ly = pad, bar_y + 36
    for name, pct, color in langs:
        parts.append(f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{color}"/>')
        parts.append(f'<text x="{lx + 16}" y="{ly}" class="legend">{name} <tspan class="pct">{pct:.1f}%</tspan></text>')
        lx += 16 + 7.3 * len(f"{name} {pct:.1f}%") + 20

    height = ly + 20
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="GitHub stats for {LOGIN}">
<style>
  text {{ font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #1f2328; }}
  .value {{ font-size: 34px; font-weight: 600; fill: #047857; letter-spacing: -0.5px; }}
  .label, .pct {{ font-size: 13px; fill: #59636e; }}
  .legend {{ font-size: 13px; }}
  @media (prefers-color-scheme: dark) {{
    text {{ fill: #f0f6fc; }}
    .value {{ fill: #34d399; }}
    .label, .pct {{ fill: #9198a1; }}
  }}
</style>
{chr(10).join(parts)}
</svg>
"""
    OUT.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT} ({calendar['totalContributions']} contributions, streak {current}/{longest})")


if __name__ == "__main__":
    render(fetch())
