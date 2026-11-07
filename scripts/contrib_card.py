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


def header_background(path, height):
    """The background layers of header.svg (backdrop, drifting glow, DNA letters, teal scan, flickering bases),
    cut to `height`. Falls back to a plain backdrop if the header is missing."""
    import re
    try:
        src = open(path).read()
    except OSError:
        return "", f'<rect width="{W}" height="{height}" rx="16" fill="{BG}"/>'
    defs = re.search(r"<defs>(.*?)</defs>", src, re.S).group(1)
    defs = re.sub(r'<linearGradient id="g".*?</linearGradient>', "", defs, flags=re.S)       # keep our own gradient
    defs = re.sub(r'(<clipPath id="scan"><rect[^>]*?)height="\d+"', rf'\1height="{height}"', defs)
    style = re.search(r"<style>(.*?)</style>", src, re.S).group(1)
    body = src[src.index("</style>") + len("</style>"):]
    stop = body.index('<g fill="url(#g)"') if '<g fill="url(#g)"' in body else len(body)   # the title starts here
    layers = body[:stop]
    layers = re.sub(r'(<rect width="\d+") height="\d+"', rf'\1 height="{height}"', layers, count=1)

    def keep(m):                                                     # drop letters below the card
        y = re.search(r'\by="([\d.]+)"', m.group(0))
        return m.group(0) if y is None or float(y.group(1)) <= height else ""
    layers = re.sub(r"<text\b[^>]*>.*?</text>", keep, layers, flags=re.S)
    return defs + f"<style>{style}</style>", layers


def render(counts, start, today, user="omarvelously", header="header.svg"):
    """A year of days drawn as a DNA sequence: one base per day, lit in the header's purple -> teal gradient by
    activity; the bases light up left to right like a sequencing read; today blinks."""
    import hashlib
    H = 280
    g0 = start if today < start + dt.timedelta(365) else today - dt.timedelta(364)
    g1 = g0 + dt.timedelta(364)
    first = g0 - dt.timedelta((g0.weekday() + 1) % 7)
    nweeks = (g1 - first).days // 7 + 1
    inside = {d: c for d, c in counts.items() if start <= d <= today}
    top = max(list(inside.values()) or [1])
    total = sum(inside.values())
    cur, best = streaks(counts, start, today)
    cal_x, cal_y = 112, 104
    step = max(11, min(22, 640 // nweeks))                          # column step
    rh = step                                                        # square grid
    hdefs, layers = header_background(header, H)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
         f'<defs>{hdefs.split("<style>")[0]}'
         f'<linearGradient id="cg" gradientUnits="userSpaceOnUse" x1="{cal_x}" x2="{W - 60}" y1="0" y2="0">'
         f'<stop offset="0" stop-color="{PURPLE}"/><stop offset="1" stop-color="{TEAL}"/></linearGradient>'
         f'<clipPath id="card"><rect width="{W}" height="{H}" rx="16"/></clipPath></defs>',
         "<style>" + (hdefs.split("<style>")[1].split("</style>")[0] if "<style>" in hdefs else "") +
         f".b{{font:700 {min(step, rh) - 1}px {MONO}}}.v{{font:800 30px {MONO}}}</style>",
         f'<g clip-path="url(#card)">', layers]
    o.append(f'<text class="lbl" x="70" y="44">&gt;{escape(user)} · {total:,} bp · since '
             f'{start.strftime("%-d %b %Y")}</text>')
    for k, nm in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        o.append(f'<text class="lbl" x="70" y="{cal_y + k * rh + step - 4}">{nm}</text>')
    last_month = None
    for w in range(nweeks):
        ws = first + dt.timedelta(7 * w)
        x = cal_x + w * step
        days = [ws + dt.timedelta(k) for k in range(7)]
        shown = [d for d in days if g0 <= d <= g1]
        firsts = [d for d in shown if d.day == 1]
        m = firsts[0] if firsts else (shown[0] if shown and w == 0 else None)
        if m is not None and m.month != last_month:
            o.append(f'<text class="lbl" x="{x}" y="{cal_y - 12}">{m.strftime("%b")}</text>')
            last_month = m.month
        colour = mix(w / max(nweeks - 1, 1))
        for k, d in enumerate(days):
            if d not in shown:
                continue
            y = cal_y + k * rh
            sq = f'x="{x}" y="{y}" width="{step - 4}" height="{step - 4}" rx="3"'
            if d > today:                                             # not yet: outline only
                o.append(f'<rect {sq} fill="none" stroke="{FG}" stroke-opacity="0.08"/>')
                continue
            c = counts.get(d, 0) if d >= start else 0
            tip = f'<title>{d.isoformat()}: {c} contribution{"" if c == 1 else "s"}</title>'
            if d == today:
                o.append(f'<rect {sq} fill="{TEAL}">{tip}<animate attributeName="opacity" values="1;.25;1" dur="1.4s" '
                         f'repeatCount="indefinite"/></rect>')
            elif c <= 0:
                o.append(f'<rect {sq} fill="{FG}" fill-opacity="0.06" stroke="{FG}" stroke-opacity="0.08">{tip}</rect>')
            else:
                op = (0.35, 0.55, 0.78, 1.0)[min(3, int(4 * c / (top + 1e-9)))]
                o.append(f'<rect {sq} fill="{colour}" opacity="0">{tip}<animate attributeName="opacity" from="0" '
                         f'to="{op}" begin="{0.4 + 0.035 * w:.2f}s" dur=".5s" fill="freeze"/></rect>')
    sx = 860
    for i, (lab, val) in enumerate((("CONTRIBUTIONS", f"{total:,}"),
                                    ("CURRENT STREAK", f"{cur} day{'s' if cur != 1 else ''}"),
                                    ("LONGEST STREAK", f"{best} day{'s' if best != 1 else ''}"))):
        y = cal_y - 22 + i * 64
        o.append(f'<text class="lbl" x="{sx}" y="{y}">{lab}</text>')
        o.append(f'<text class="v" x="{sx}" y="{y + 34}" fill="url(#cg)">{escape(val)}</text>')
    ty = cal_y + 7 * rh + 50
    line = f"updated {today.isoformat()}"
    o.append(f'<text class="ty" x="70" y="{ty}"><tspan fill="{TEAL}">&gt;</tspan> {line}</text>')
    cx = 70 + 14.45 * (len(line) + 2) + 4                              # 24px mono advance ~14.45px
    o.append(f'<rect x="{cx:.0f}" y="{ty - 20}" width="12" height="26" fill="{TEAL}">'
             f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1s" '
             f'repeatCount="indefinite"/></rect>')
    o.append("</g></svg>")
    return "\n".join(o)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", default="omarvelously")
    p.add_argument("--start", default="2026-09-29")
    p.add_argument("--out", default="contributions.svg")
    p.add_argument("--header", default="header.svg", help="background is taken from this SVG")
    p.add_argument("--tz", default="Asia/Shanghai", help="time zone that decides which day is 'today'")
    a = p.parse_args()
    from zoneinfo import ZoneInfo
    today = dt.datetime.now(ZoneInfo(a.tz)).date()
    start = dt.date.fromisoformat(a.start)
    counts = fetch(a.user, start, today, os.environ["GH_TOKEN"])
    svg = render(counts, start, today, a.user, a.header)
    with open(a.out, "w") as f:
        f.write(svg)
    print(f"wrote {a.out}: {sum(c for d, c in counts.items() if start <= d <= today)} contributions, "
          f"streaks {streaks(counts, start, today)}")


if __name__ == "__main__":
    main()
