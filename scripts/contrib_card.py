"""Draw the profile's contribution calendar and streaks since a start date, as an SVG.

Reads the contribution calendar from GitHub's GraphQL API (token in GH_TOKEN; no scopes needed) and writes a card with
the daily squares, total contributions, current streak and longest streak. No averages.

    GH_TOKEN=... python scripts/contrib_card.py --user omarvelously --start 2026-09-29 --out contributions.svg
"""
import argparse
import datetime as dt
import json
import os
import urllib.request
from xml.sax.saxutils import escape

QUERY = """query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) { contributionsCollection(from: $from, to: $to) {
    contributionCalendar { weeks { contributionDays { date contributionCount } } } } } }"""
PURPLE, TEAL, BG, FG, MUTED = "#a371f7", "#2dd4bf", "#0b0f17", "#e6edf3", "#8b949e"   # header.svg palette
MONO = "'JetBrains Mono','SFMono-Regular',Menlo,Consolas,'Liberation Mono',monospace"
W = 1204


def fetch_range(user, start, end, token):
    body = json.dumps({"query": QUERY, "variables": {
        "login": user, "from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "contrib-card"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return {dt.date.fromisoformat(d["date"]): d["contributionCount"] for w in weeks for d in w["contributionDays"]}


def fetch(user, start, end, token):
    """The API returns at most one year per call: fetch in chunks."""
    out, a = {}, start
    while a <= end:
        b = min(end, a + dt.timedelta(days=360))
        out.update({d: c for d, c in fetch_range(user, a, b, token).items() if a <= d <= b})
        a = b + dt.timedelta(days=1)
    return out


def streaks(counts, start, today):
    """Longest run of days with contributions in [start, today]; current run ends today, or yesterday if today has
    none yet (a day in progress does not break the streak)."""
    days = [start + dt.timedelta(i) for i in range((today - start).days + 1)]
    best = run = 0
    for d in days:
        run = run + 1 if counts.get(d, 0) > 0 else 0
        best = max(best, run)
    cur, d = 0, today if counts.get(today, 0) > 0 else today - dt.timedelta(1)
    while d >= start and counts.get(d, 0) > 0:
        cur, d = cur + 1, d - dt.timedelta(1)
    return cur, best


def mix(t):
    """Purple -> teal at t in [0, 1] (the header's left-to-right gradient)."""
    a = [int(PURPLE[k:k + 2], 16) for k in (1, 3, 5)]
    b = [int(TEAL[k:k + 2], 16) for k in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def render(counts, start, today, user="omarvelously"):
    import random
    # the grid always shows a full year of days: from `start` for its first year (future days as outlines), then the
    # last 365 days
    g0 = start if today < start + dt.timedelta(365) else today - dt.timedelta(364)
    g1 = g0 + dt.timedelta(364)
    first = g0 - dt.timedelta((g0.weekday() + 1) % 7)                # Sunday of the first week (GitHub layout)
    nweeks = (g1 - first).days // 7 + 1
    inside = {d: c for d, c in counts.items() if start <= d <= today}
    top = max(list(inside.values()) or [1])
    total = sum(inside.values())
    cur, best = streaks(counts, start, today)
    cal_x, cal_y, avail = 112, 92, 600
    step = max(12, min(26, avail // max(nweeks, 1)))                 # square + gap, shrinks as weeks accumulate
    cell = step - 4
    H = max(300, cal_y + 7 * step + 56)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
         '<defs>',
         f'<linearGradient id="g" gradientUnits="userSpaceOnUse" x1="{cal_x}" x2="{W - 80}" y1="0" y2="0">'
         f'<stop offset="0" stop-color="{PURPLE}"/><stop offset="1" stop-color="{TEAL}"/></linearGradient>',
         f'<radialGradient id="glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{PURPLE}" stop-opacity=".28"/>'
         f'<stop offset="1" stop-color="{PURPLE}" stop-opacity="0"/></radialGradient>',
         '</defs>',
         f'<style>.w{{font:13px {MONO}}}.lbl{{font:12px {MONO};fill:{MUTED};letter-spacing:1px}}'
         f'.v{{font:800 30px {MONO}}}.ty{{font:15px {MONO};fill:{FG}}}</style>',
         f'<rect width="{W}" height="{H}" rx="16" fill="{BG}"/>',
         f'<circle cx="{W * .42:.0f}" cy="{H * .45:.0f}" r="420" fill="url(#glow)"/>']
    rng = random.Random(7)                                            # fixed seed: the backdrop never changes
    xs = " ".join(str(3 + 14 * k) for k in range(86))
    for r in range(17):
        seq = "".join(rng.choice("ACGT") for _ in range(86))
        o.append(f'<text class="w" fill="{FG}" fill-opacity="0.075" y="{13 + 18 * r}" x="{xs}">{seq}</text>')
    o.append(f'<text class="lbl" x="70" y="44">&gt;{escape(user)} · contributions since '
             f'{start.strftime("%-d %b %Y")}</text>')
    for k, nm in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        o.append(f'<text class="lbl" x="70" y="{cal_y + k * step + cell - 3}">{nm}</text>')
    last_month = None
    for w in range(nweeks):
        ws = first + dt.timedelta(7 * w)
        x = cal_x + w * step
        days = [ws + dt.timedelta(k) for k in range(7)]
        shown = [d for d in days if g0 <= d <= g1]
        firsts = [d for d in shown if d.day == 1]
        m = firsts[0] if firsts else (shown[0] if shown and w == 0 else None)
        if m is not None and m.month != last_month:
            o.append(f'<text class="lbl" x="{x}" y="{cal_y - 10}">{m.strftime("%b")}</text>')
            last_month = m.month
        colour = mix(w / max(nweeks - 1, 1))
        for k, d in enumerate(days):
            if d not in shown:
                continue
            if d > today:                                             # not yet: outline only
                o.append(f'<rect x="{x}" y="{cal_y + k * step}" width="{cell}" height="{cell}" rx="3" fill="none" '
                         f'stroke="{FG}" stroke-opacity="0.07"/>')
                continue
            c = counts.get(d, 0) if d >= start else 0                 # activity counted from `start`
            tip = f'<title>{d.isoformat()}: {c} contribution{"" if c == 1 else "s"}</title>'
            if c <= 0:
                o.append(f'<rect x="{x}" y="{cal_y + k * step}" width="{cell}" height="{cell}" rx="3" fill="{FG}" '
                         f'fill-opacity="0.06" stroke="{FG}" stroke-opacity="0.08">{tip}</rect>')
            else:
                op = (0.35, 0.55, 0.78, 1.0)[min(3, int(4 * c / (top + 1e-9)))] if top > 0 else 1.0
                o.append(f'<rect x="{x}" y="{cal_y + k * step}" width="{cell}" height="{cell}" rx="3" fill="{colour}" '
                         f'fill-opacity="{op}">{tip}</rect>')
    sx = 820
    for i, (lab, val) in enumerate((("CONTRIBUTIONS", f"{total:,}"),
                                    ("CURRENT STREAK", f"{cur} day{'s' if cur != 1 else ''}"),
                                    ("LONGEST STREAK", f"{best} day{'s' if best != 1 else ''}"))):
        y = cal_y + 6 + i * 62
        o.append(f'<text class="lbl" x="{sx}" y="{y}">{lab}</text>')
        o.append(f'<text class="v" x="{sx}" y="{y + 34}" fill="url(#g)">{escape(val)}</text>')
    ty = cal_y + 7 * step + 34
    o.append(f'<text class="ty" x="70" y="{ty}"><tspan fill="{TEAL}">&gt;</tspan> updated {today.isoformat()}</text>')
    o.append("</svg>")
    return "\n".join(o)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", default="omarvelously")
    p.add_argument("--start", default="2026-09-29")
    p.add_argument("--out", default="contributions.svg")
    p.add_argument("--tz", default="Asia/Shanghai", help="time zone that decides which day is 'today'")
    a = p.parse_args()
    from zoneinfo import ZoneInfo
    today = dt.datetime.now(ZoneInfo(a.tz)).date()
    start = dt.date.fromisoformat(a.start)
    counts = fetch(a.user, start, today, os.environ["GH_TOKEN"])
    svg = render(counts, start, today)
    with open(a.out, "w") as f:
        f.write(svg)
    print(f"wrote {a.out}: {sum(c for d, c in counts.items() if start <= d <= today)} contributions, "
          f"streaks {streaks(counts, start, today)}")


if __name__ == "__main__":
    main()
