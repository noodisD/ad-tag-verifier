"""Command line for the capture / analyze / report engine.

    python -m core.cli profile  <url> [--viewport mobile]
    python -m core.cli capture  --url <url> [--expect ID] [--viewport mobile]
    python -m core.cli capture  --jobs jobs.json
    python -m core.cli analyze  <run_dir>
    python -m core.cli report   <run_dir> [-o report.html]

`profile` runs no browser — it just prints how a URL would be driven, which is
the cheapest way to confirm a new publisher entry does what you meant.
"""

import argparse
import json
import sys
from pathlib import Path

# The verdict table prints ✅/❌. On a Polish Windows console stdout defaults to
# cp1250, which has no codepoint for either — printing one raises
# UnicodeEncodeError and takes down the run *after* a 150s capture has already
# finished. Force UTF-8 before anything can print. Regression: core/tests/
# test_cli_encoding.py
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # already wrapped / not a TextIOWrapper
        pass

from core import profiles
from core.analyze import findings


def cmd_profile(args):
    for url in args.urls:
        print(f"{url[:88]}\n    {profiles.describe(url, args.viewport)}")
    return 0


def _load_jobs(args):
    if args.jobs:
        with open(args.jobs, encoding="utf-8") as f:
            jobs = json.load(f)
        return jobs if isinstance(jobs, list) else jobs.get("targets", [])
    return [{
        "id": args.id or "target-1",
        "label": args.label or (args.url[:40]),
        "url": args.url,
        "expected_id": args.expect,
        "viewport": args.viewport,
    }]


def _overrides(args, job):
    """Per-run settings the profile cannot know: who the campaign belongs to,
    and therefore whether the vision fallback can be used at all.

    Without an advertiser the model has no way to tell this campaign's
    creative from the three others on the page, so it is not asked — which is
    why a CLI run could never attempt the click that the API path could.
    """
    advertiser = job.get("advertiser") or getattr(args, "advertiser", None)
    if not advertiser:
        return None
    out = {"advertiser": advertiser}
    try:
        from core.ai import creative_click, match as ai_match
        eye = creative_click.VisionMatcher(ai_match.default_model())
        if eye.available:
            out["vision"] = eye
    except Exception:
        pass
    return out


def cmd_capture(args):
    from playwright.sync_api import sync_playwright
    from core.capture import session

    jobs = _load_jobs(args)
    if not jobs:
        print("no targets"); return 1

    run_dir = session.new_run_dir(args.out, args.campaign)
    print(f"run: {run_dir}\n")

    # watch mode needs a visible window; nothing to watch in headless.
    any_watch = any(profiles.resolve(j["url"], j.get("viewport", "desktop"))["strategy"] == "watch"
                    for j in jobs)
    headless = args.headless and not any_watch
    if any_watch and args.headless:
        print("note: a target uses the watch strategy — running headed\n")

    metas = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless, args=["--disable-blink-features=AutomationControlled"])
        for j in jobs:
            vp = j.get("viewport", args.viewport)
            print(f"  {j.get('label', j['id'])[:44]:<45} {profiles.describe(j['url'], vp)}")
            meta = session.capture(j, browser, run_dir, viewport=vp,
                                   overrides=_overrides(args, j))
            fired = [b for b in meta["beacons"] if b["evidence"] == "fired"]
            print(f"      {len(fired)} beacons fired in {meta['duration_s']}s"
                  f"{'  ERROR: ' + meta['error'] if meta['error'] else ''}")
        browser.close()

    print()
    results = findings.analyze_run(run_dir, require_click=not args.no_click)
    print(findings.render_table(results))
    print(f"\nartifacts: {run_dir}")
    return 0


def cmd_analyze(args):
    results = findings.analyze_run(args.run_dir, require_click=not args.no_click)
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(findings.render_table(results))
    return 0


def cmd_report(args):
    from core.report import html
    results = findings.analyze_run(args.run_dir, require_click=not args.no_click)
    out = Path(args.out or Path(args.run_dir) / "report.html")
    html.write(results, out, campaign=Path(args.run_dir).name)
    print(f"wrote {out}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="core.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("profile", help="show how a URL would be driven")
    p.add_argument("urls", nargs="+")
    p.add_argument("--viewport", default="desktop", choices=["desktop", "mobile"])
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("capture", help="run targets and write artifacts")
    p.add_argument("--url")
    p.add_argument("--id")
    p.add_argument("--label")
    p.add_argument("--expect", help="expected bn / placement id")
    p.add_argument("--jobs", help="json file with a list of targets")
    p.add_argument("--viewport", default="desktop", choices=["desktop", "mobile"])
    p.add_argument("--out", default="core/artifacts")
    p.add_argument("--campaign", default="run")
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--headed", dest="headless", action="store_false")
    p.add_argument("--no-click", action="store_true")
    p.add_argument("--advertiser",
                   help="who the campaign belongs to; enables the vision click fallback")
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("analyze", help="re-read artifacts, no browser")
    p.add_argument("run_dir")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-click", action="store_true")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("report", help="render an HTML report")
    p.add_argument("run_dir")
    p.add_argument("-o", "--out")
    p.add_argument("--no-click", action="store_true")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
