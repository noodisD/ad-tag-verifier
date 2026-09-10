"""Profile resolution — how a URL decides the way it gets driven."""

from core import profiles


class TestComposition:
    """Profiles merge rather than first-match-wins, so a publisher's timing
    and a URL shape's strategy can be stated once each instead of once per
    pairing."""

    def test_domain_and_url_shape_both_apply(self):
        s = profiles.resolve(
            "https://tvn24.pl/article?google_preview=abc&iu=123")
        assert s["strategy"] == "gam_preview"      # from the URL shape
        assert s["patience"] == 80                 # from the publisher
        assert {"tvn", "gam-preview"} <= set(s["profiles_applied"])

    def test_plain_publisher_url_keeps_default_strategy(self):
        s = profiles.resolve("https://tvn24.pl/some-article-1234567")
        assert s["strategy"] == "load"
        assert s["patience"] == 80


class TestMeasuredPatience:
    def test_infor_waits_long_enough_for_a_96s_impression(self):
        # Measured on dziennik.pl: the impression fired at 96.9s. The old
        # backend allowed ~9s and reported the page as carrying no tags.
        s = profiles.resolve("https://www.dziennik.pl/?version=300x250-bankclient")
        assert s["patience"] > 96.9

    def test_creative_preview_is_cheap(self):
        # Isolated creative, nothing competing — no reason to wait as long as
        # a live portal page. Not as short as 25s either: an Adquery preview
        # logged "impression NOT seen within 25s" and then fired, so the run
        # skipped the click on a creative that had rendered.
        s = profiles.resolve(
            "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.1")
        assert 30 <= s["patience"] <= 50
        assert s["strategy"] == "load"


class TestStrategySelection:
    def test_gam_preview_detected_by_query_param_on_any_domain(self):
        for url in ["https://www.gazeta.pl/0,0.html?google_preview=abc",
                    "https://www.bankier.pl/?live_preview_config={}"]:
            assert profiles.resolve(url)["strategy"] == "gam_preview"

    def test_commercial_break_needs_navigation(self):
        url = "https://kobieta.wp.pl?tcidma=x/Baner_Commercial_Break/1730599&testPos=2"
        assert profiles.resolve(url)["strategy"] == "navigation_click"

    def test_sandboxed_preview_goes_to_watch_and_skips_clicking(self):
        # The sandbox blocks navigation by design; an automated click there
        # yields a "fail" that says nothing about the tag.
        s = profiles.resolve("https://preview.adnami.io/pv?guid=abc")
        assert s["strategy"] == "watch"
        assert s["click"] is False


class TestViewport:
    """Viewport comes from the job, never guessed from the URL — the same URL
    is a different test on mobile, and a mobile placement cannot serve at all
    in a desktop viewport."""

    def test_mobile_sets_emulation_flags(self):
        s = profiles.resolve("https://tvn24.pl/x", viewport="mobile")
        assert s["viewport"]["is_mobile"] is True
        assert s["viewport"]["has_touch"] is True
        assert "Mobile Safari" in s["viewport"]["user_agent"]

    def test_desktop_is_not_mobile(self):
        s = profiles.resolve("https://tvn24.pl/x", viewport="desktop")
        assert s["viewport"]["is_mobile"] is False

    def test_same_url_differs_only_by_viewport(self):
        url = "https://tvn24.pl/x"
        assert (profiles.resolve(url, "desktop")["viewport"]["width"]
                != profiles.resolve(url, "mobile")["viewport"]["width"])


class TestLinkExclusion:
    def test_wp_excludes_pages_that_break_a_run(self):
        # Shop / login / live-stream pages are not articles; navigating to one
        # tears the session down without ever showing the overlay.
        rx = profiles.resolve("https://kobieta.wp.pl/x")["exclude_links"]
        import re
        for bad in ["https://kup.tvn24.pl/oferta", "https://wp.pl/plus/zaloguj",
                    "https://wp.pl/newslettery"]:
            assert re.search(rx, bad, re.I), bad


def test_wp_preview_links_still_attempt_the_click_automatically():
    """Frame targeting finds nothing on WP's large formats, but the vision
    fallback gets a turn and its result is checked against the beacon — so
    trying costs nothing and not trying guarantees an untested click."""
    s = profiles.resolve(
        "https://wiadomosci.wp.pl?wfName=281086_3065732_FuelClient&creName=giga_desktop")
    assert s["strategy"] == "load"
    assert s["patience"] == 70, "still inherits WP's measured patience"
    assert s.get("watch_timeout") == 180, "watch stays configured as the backstop"


def test_an_ordinary_wp_article_is_still_automated():
    """Only the preview links go to watch — the domain profile must not drag
    every WP page into a mode that needs a human."""
    s = profiles.resolve("https://wiadomosci.wp.pl/artykul/cos")
    assert s["strategy"] == "load"


# ── instream ─────────────────────────────────────────────────────────────

def test_gam_video_preview_matches_url_encoded_parameter():
    """A video preview carries `google_preview` inside `redirect=`, encoded.

    Matching only the decoded `google_preview=` missed every TVP link, which
    then ran as a plain load: no play, no pre-roll, "no tags fired".
    """
    s = profiles.resolve(
        "https://pubads.g.doubleclick.net/gampad/preview_cookie?op=set"
        "&redirect=https://vod.tvp.pl/seriale,18/x?google_preview%3DABC"
        "&lineItemId=7409881638")
    assert "gam-preview" in s["profiles_applied"]


def test_vod_pages_use_the_video_strategy():
    for url in ("https://vod.tvp.pl/seriale,18/pan-mama-odcinki,1907785/odcinek-58",
                "https://tvn.adocean.pl/readredir/id=T6xW/forcecookie=1/url=AQAA"):
        s = profiles.resolve(url)
        assert s["strategy"] == "video", url
        # Measured: consent at 5s, VAST at 33s, quartiles out to 64s, and a
        # player that boots in 30s or in 232s depending on whether anyone is
        # looking at the tab.
        assert s["patience"] >= 180, url


def test_video_needs_a_window():
    """bring_to_front is meaningless headless, and that is where the
    measurement came from."""
    from core.capture import strategies
    assert "video" in strategies.NEEDS_WINDOW
