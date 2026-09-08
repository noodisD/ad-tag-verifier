"""Self-contained HTML report.

Written to be forwarded to a publisher as-is: one file, screenshots embedded,
and the exact beacon URLs quoted rather than summarized. A verdict is only
worth arguing about if the evidence travels with it.
"""

import base64
import html as _html
import json
from datetime import datetime
from pathlib import Path

from core.analyze.findings import (PASS, IMPRESSION_ONLY, MISSING, WRONG_TAG,
                                   INCONCLUSIVE, VERDICT_LABEL)

CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a18;--mut:#6b6b66;--line:#e2e2dd;--card:#fff;
--ok:#1a7f4b;--warn:#b06b00;--bad:#b3261e;--info:#2a5fa5}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 24px 64px}
h1{font-size:21px;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--mut);font-size:13px;margin-bottom:24px}
.tally{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:28px}
.chip{border:1px solid var(--line);background:var(--card);border-radius:999px;
padding:5px 13px;font-size:12.5px}
.chip b{font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
margin-bottom:14px;overflow:hidden}
.head{display:flex;align-items:center;gap:12px;padding:13px 16px;
border-bottom:1px solid var(--line);flex-wrap:wrap}
.name{font-weight:600;flex:1;min-width:180px}
.badge{font-size:11.5px;font-weight:600;padding:3px 9px;border-radius:5px;
text-transform:uppercase;letter-spacing:.03em;white-space:nowrap}
.b-pass{background:#e7f4ec;color:var(--ok)}
.b-imp{background:#fdf1de;color:var(--warn)}
.b-bad{background:#fdeceb;color:var(--bad)}
.b-inc{background:#eef1f5;color:var(--info)}
.meta{font-size:12px;color:var(--mut)}
.body{padding:14px 16px;display:grid;grid-template-columns:1fr auto;gap:18px}
@media(max-width:720px){.body{grid-template-columns:1fr}}
dl{margin:0;display:grid;grid-template-columns:96px 1fr;gap:5px 14px;
font-size:12.5px;align-items:baseline}
dt{color:var(--mut)}
dd{margin:0;word-break:break-all;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
font-size:11.5px}
.miss{color:var(--mut);font-style:italic;font-family:inherit;font-size:12.5px}
.shot{max-width:260px;border:1px solid var(--line);border-radius:6px;display:block}
.note{margin:10px 16px 14px;padding:9px 12px;border-radius:6px;font-size:12.5px;
background:#fdf1de;color:#7a4a00;border:1px solid #f0dcb8}
.note.bad{background:#fdeceb;color:#8c1d18;border-color:#f5cdc9}
footer{margin-top:30px;padding-top:16px;border-top:1px solid var(--line);
color:var(--mut);font-size:12px}
code{background:#f1f1ee;padding:1px 5px;border-radius:4px;font-size:11.5px}
"""

BADGE = {PASS: "b-pass", IMPRESSION_ONLY: "b-imp", MISSING: "b-bad",
         WRONG_TAG: "b-bad", INCONCLUSIVE: "b-inc"}


def _esc(s):
    return _html.escape(str(s)) if s is not None else ""


def _img(run_dir, name):
    if not name:
        return ""
    p = Path(run_dir) / name
    if not p.exists() or p.stat().st_size > 3_000_000:
        return ""
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f'<img class="shot" src="data:image/png;base64,{b64}" alt="">'


def _beacon_row(label, beacon):
    if not beacon:
        return f"<dt>{label}</dt><dd class='miss'>not observed</dd>"
    t = beacon.get("started") or ""
    when = f" <span class='meta'>({t[11:19]})</span>" if len(t) > 19 else ""
    return f"<dt>{label}</dt><dd>{_esc(beacon['url'][:190])}{when}</dd>"


def render(results, campaign="run"):
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    chips = "".join(
        f'<span class="chip"><b>{n}</b> {_esc(VERDICT_LABEL[v])}</span>'
        for v, n in sorted(counts.items(), key=lambda kv: -kv[1]))

    cards = []
    for r in results:
        badge = BADGE.get(r["verdict"], "b-inc")
        rows = [
            f"<dt>expected</dt><dd>{_esc(r['expected_id'] or '—')}</dd>",
            _beacon_row("impression", r["impression"]),
            _beacon_row("click", r["click"]),
        ]
        if r.get("landing"):
            rows.append(f"<dt>landing</dt><dd>{_esc(r['landing'][:190])}</dd>")
        if r.get("measurement_vendors"):
            rows.append("<dt>measurement</dt><dd>"
                        f"{_esc(', '.join(r['measurement_vendors']))}</dd>")
        rows.append("<dt>how</dt><dd>"
                    f"{_esc(r.get('strategy'))} / {_esc(r.get('viewport'))} / "
                    f"{_esc(r.get('duration_s'))}s</dd>")

        notes = []
        if r["verdict"] == WRONG_TAG:
            notes.append(
                '<div class="note bad">The expected tag never fired, but '
                f"another serving tag did in its place: <code>"
                f"{_esc(', '.join(r['other_serving_ids'][:4]))}</code>. "
                "That is the right slot running the wrong tag.</div>")
        elif r["verdict"] == IMPRESSION_ONLY:
            notes.append(
                '<div class="note">Impression confirmed; the click tag was not '
                "observed. On a page carrying several competing slots this is "
                "often a limitation of automated clicking rather than a missing "
                "tag — worth confirming by hand before reporting it.</div>")
        if r.get("impression_in_markup_only"):
            notes.append(
                '<div class="note">The ID appears in the page source but no '
                "request was ever made for it. Present in markup is not the "
                "same as fired.</div>")
        if r.get("error"):
            notes.append(f'<div class="note bad">Run error: {_esc(r["error"])}</div>')

        cards.append(f"""
<div class="card">
  <div class="head">
    <span class="name">{_esc(r['label'])}</span>
    <span class="meta">{_esc((r['url'] or '')[:74])}</span>
    <span class="badge {badge}">{_esc(VERDICT_LABEL[r['verdict']])}</span>
  </div>
  <div class="body">
    <dl>{''.join(rows)}</dl>
    <div>{_img(r.get('dir'), r.get('screenshot'))}</div>
  </div>
  {''.join(notes)}
</div>""")

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Tag verification — {_esc(campaign)}</title>
<style>{CSS}</style>
<div class="wrap">
  <h1>Tag verification</h1>
  <div class="sub">{_esc(campaign)} · {stamp} · {len(results)} placements</div>
  <div class="tally">{chips}</div>
  {''.join(cards)}
  <footer>
    Each verdict comes from the network log recorded while the page ran; the
    full HAR sits beside this file and opens in any browser's devtools.
    An impression is counted only when the beacon was actually requested —
    an ID present in page source is reported separately and never as a pass.
  </footer>
</div>"""


def write(results, out_path, campaign="run"):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(results, campaign), encoding="utf-8")
    return out_path
