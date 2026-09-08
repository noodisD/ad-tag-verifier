# core — capture / analyze / report

The engine `scripts/` grew into. Same job, reorganized around one rule: **the
browser produces evidence and decides nothing.** Verdicts come from reading
that evidence afterwards.

## Why it is split this way

The 126 scripts in `scripts/` each open a browser, judge what they see, and
print the result. Three costs follow from that, and all three were paid
repeatedly:

- **A wrong detection rule costs a full re-run.** Working out that
  `securepubads.g.doubleclick.net` is Ad Manager's own infrastructure rather
  than a CM360 beacon meant re-driving every page to re-check. Here it costs
  one re-read: capture took **156s** on a live publisher page, re-analysis of
  the stored artifact takes **0.5s**.
- **Evidence evaporates.** A verdict printed to stdout is not something you
  can send a publisher who disagrees. Now every run leaves a HAR they can open
  in their own devtools.
- **Nothing is testable.** There is no way to write a regression test against
  a live page. There is one against a stored HAR — `core/tests/` pins every
  classification rule that has been got wrong.

Borrowed from [Publisher Ads Lighthouse Plugin](https://github.com/googleads/publisher-ads-lighthouse-plugin)
(gatherers produce artifacts, audits read them), Playwright's native
[HAR recording](https://playwright.dev/python/docs/mock), and Scrapy's
config-driven per-site adapters.

## Layout

```
profiles.yaml     per-site behaviour — adding a publisher is an entry, not code
profiles.py       resolves a URL to merged settings
capture/
  session.py      one session -> one artifact (run.har + meta.json + screenshot)
  strategies.py   load / gam_preview / navigation_click / watch
  consent.py      getting past the consent wall
analyze/
  vendors.py      what each vendor's beacons look like, split impression/click
  findings.py     artifact -> verdict. No browser.
report/html.py    one self-contained file, screenshots embedded
tests/            fast, browser-free
```

## Use

```bash
python -m core.cli profile "<url>"                 # how would this be driven?
python -m core.cli capture --url "<url>" --expect 90069259 --viewport mobile
python -m core.cli analyze core/artifacts/<run>    # re-read, no browser
python -m core.cli report  core/artifacts/<run>
python -m pytest core/tests -q
```

`profile` runs no browser — it is the cheapest way to confirm a new
`profiles.yaml` entry does what you meant.

## The four strategies

| Strategy | For | Why it exists |
|---|---|---|
| `load` | isolated creative previews | The case automation handles perfectly |
| `gam_preview` | `google_preview=`, `live_preview_config` | First load only sets the preview cookie; the creative renders on the second. Loading once and reporting nothing is a false negative |
| `navigation_click` | Commercial Break overlays | Only appear on a real in-page navigation. `page.goto()` never triggers them, and a synthetic `element.click()` is ignored because it carries `isTrusted=false` |
| `watch` | competing slots, sandboxed previews | The browser is handed to a person; the tool only records |

`watch` is a deliberate limit, not a gap. On pages carrying several
same-size slots, automated clicking repeatedly clicked *other advertisers'*
creatives and reported them as the campaign's. Four successive targeting
methods — by size, by frame content, by the frame that fired the impression,
and clicking within a second of it — all failed the same way, because the slot
can be refreshed between the impression and the click. A person clicks
correctly in seconds; capturing the evidence is the part worth automating.

## What counts as a pass

An impression counts only when the beacon was **actually requested**. An ID
merely present in page source is recorded as `in_markup` and never as a pass —
on a live page that markup frequently belongs to a different advertiser.

When the expected tag never fires but another serving tag does in its place,
that is reported as `WRONG TAG in slot` rather than a plain miss. That is the
failure this is really for.

## Artifacts are not committed

A run artifact carries real campaign IDs and publisher URLs. HARs are recorded
in `minimal` mode, which omits response bodies and cookies, but they are still
campaign data — `core/artifacts/` is gitignored. Test fixtures under
`core/tests/fixtures/` are the deliberate exception and must be sanitized
first.
