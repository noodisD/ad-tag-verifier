"""Resolve a test URL to the settings that drive it.

Every profile whose `match` string appears in the URL applies, merged in file
order so later entries win. That composition is deliberate: a TVN Commercial
Break URL needs TVN's patience *and* the navigation-click strategy, and those
are two separate concerns that shouldn't have to be written out as a combined
profile for every pairing.
"""

from pathlib import Path
import yaml

CONFIG_PATH = Path(__file__).with_name("profiles.yaml")

_cache = None


def _config():
    global _cache
    if _cache is None:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            _cache = yaml.safe_load(f)
    return _cache


def _match_strings(profile):
    m = profile.get("match", [])
    return [m] if isinstance(m, str) else list(m)


def resolve(url, viewport="desktop", overrides=None):
    """Return the merged settings dict for `url`.

    `viewport` is 'desktop' | 'mobile' (or a dict to use verbatim). It comes
    from the job, not the URL — the same page is a different test on mobile,
    and guessing it from the URL is how mobile placements end up checked in a
    desktop viewport where they cannot serve at all.
    """
    cfg = _config()
    settings = dict(cfg.get("defaults", {}))
    applied = []

    low = url.lower()
    for profile in cfg.get("profiles", []):
        if any(m.lower() in low for m in _match_strings(profile)):
            applied.append(profile.get("name", "?"))
            settings.update({k: v for k, v in profile.items()
                             if k not in ("match", "name")})

    if isinstance(viewport, dict):
        settings["viewport"] = viewport
        settings["viewport_name"] = "custom"
    else:
        vp = cfg.get("viewports", {}).get(viewport)
        if vp is None:
            raise ValueError(f"unknown viewport: {viewport}")
        settings["viewport"] = dict(vp)
        settings["viewport_name"] = viewport

    if overrides:
        settings.update(overrides)

    settings["profiles_applied"] = applied
    return settings


def describe(url, viewport="desktop"):
    """One-line summary, for the plan preview and run logs."""
    s = resolve(url, viewport)
    names = ", ".join(s["profiles_applied"]) or "defaults"
    return (f"{s['strategy']:<18} patience={s['patience']:>3}s  "
            f"{s['viewport_name']:<8} [{names}]")
