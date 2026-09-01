"""Test click tag capture on DV360 preview + debug NO TAG rows."""
from playwright.sync_api import sync_playwright
import re, time

AD_ID = "900000010"
# Row 1 (works) vs row 6 (NO TAG) vs row 9 (NO TAG)
TESTS = [
    ("row1 (IMP ok)", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.900000027&ecId=AOgHqNolVkg2BYypP1stJ4nTrHblaho2qB1NOka7n3ls0GJnj8AM4rYVcdp8ILSL8es8NLybv5fZjUwfE9_Yhjgdn9MgtcUVLQ%3D%3D&eftd=1&dv3b=IPeutP0FMMiXiLsC&flexHeight=250&flexWidth=300"),
    ("row6 (NO TAG)", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.900000030&ecId=AOgHqNonq6qGEpyV43ce4lkwsMw8fmFs6WCvAVrD0RTtvP--3wwlK3s0dbcdu-3_FWk4x3s9-MGjhYh8dYZ1fawg295FTDaiVA%3D%3D&eftd=1&dv3b=IPeutP0FMMiXiLsC&flexHeight=90&flexWidth=728"),
    ("row9 (NO TAG)", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.900000043&ecId=AOgHqNrclc4dOGNCHJyBPMWRpsbtiqHMkptOM6LthTNf2BbQrC8F7Eg2QLyakb6ueXisfK686XHN5_z661w7pHz7UeU2Ralt7A%3D%3D&eftd=1&dv3b=IPeutP0FMMiXiLsC&flexHeight=300&flexWidth=300"),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    for label, url in TESTS:
        print(f"\n{'='*60}")
        print(f"[{label}]")
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="pl-PL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = ctx.new_page()
        seen = []
        t0 = time.time()

        def on_req(req):
            u = req.url
            if 'doubleclick' not in u and 'adform' not in u:
                return
            t = time.time() - t0
            m = re.search(r'dc_trk_aid=(\d+)', u)
            short = u[:110]
            tag = ""
            if m and m.group(1) == AD_ID:
                tag = " <<< MATCH"
            if u not in seen:
                seen.append(u)
                print(f"  [t+{t:.1f}s] {short}{tag}")

        page.on("request", on_req)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print(f"  [load error] {e}")

        print(f"  Loaded. Frames: {len(page.frames)}")
        for f in page.frames:
            print(f"    frame: {f.url[:80]}")

        time.sleep(5)

        # Attempt click on various positions
        print("  >> Clicking center of page...")
        try:
            page.mouse.click(640, 450)
        except: pass
        time.sleep(3)

        # Try clicking on each iframe
        print("  >> Clicking on iframe elements...")
        try:
            iframes = page.locator("iframe").all()
            print(f"     Found {len(iframes)} iframe(s)")
            for iframe in iframes:
                try:
                    box = iframe.bounding_box()
                    if box:
                        print(f"     iframe box: x={box['x']:.0f} y={box['y']:.0f} w={box['width']:.0f} h={box['height']:.0f}")
                        cx = box['x'] + box['width']/2
                        cy = box['y'] + box['height']/2
                        page.mouse.click(cx, cy)
                        time.sleep(1)
                except Exception as e:
                    print(f"     iframe click error: {e}")
        except Exception as e:
            print(f"     Error: {e}")

        time.sleep(5)
        print(f"  Total requests seen: {len(seen)}")

        # DOM scan for click URL
        print("  >> DOM scan for trackclk...")
        for frame in page.frames:
            try:
                r = frame.evaluate("""(id) => {
                    const h = document.documentElement ? document.documentElement.outerHTML : '';
                    const clk = h.includes('trackclk');
                    const match = h.includes('dc_trk_aid=' + id);
                    const sample = (() => {
                        const i = h.indexOf('trackclk');
                        if (i < 0) return null;
                        return h.substring(i, i+150);
                    })();
                    return {clk, match, sample, len: h.length};
                }""", AD_ID)
                if r['clk']:
                    print(f"    frame {frame.url[:60]}: trackclk={r['clk']} id_match={r['match']} sample={r['sample']}")
                if r['match']:
                    print(f"    frame {frame.url[:60]}: ID {AD_ID} FOUND")
            except Exception as e:
                print(f"    frame eval error: {e}")

        page.close()
        ctx.close()

    browser.close()
print("\nDone.")
