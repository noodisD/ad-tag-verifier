"""
THE BANKING CLIENT — Sample HTML banner verification (tests.sampledata.pl)
Reads CLK (clickTag) and IMP (adfserve img) directly from page HTML.
"""

import re, requests

# Expected bn from sample_21706_THE BANKING CLIENT Excel (blis- creatives)
# 160x160 is NOT in the Excel — reported as "no reference"
EXPECTED = {
    ("120x600", "faul"):      "90000001",
    ("120x600", "gips"):      None,  # no 'gips' in Excel — will compare vs trampolina
    ("120x600", "hejt"):      "90000002",
    ("120x600", "hulajnoga"): "90000003",
    ("160x160", "faul"):      None,  # 160x160 not in Excel
    ("160x160", "gips"):      None,
    ("160x160", "hejt"):      None,
    ("160x160", "hulajnoga"): None,
}

# For reference: trampolina bn (probable match for 'gips' based on WP pattern)
TRAMPOLINA = {"120x600": "90000004", "160x600": "90000005"}

URLS = [
    ("120x600", "faul",      "https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/120x600_faul/"),
    ("120x600", "gips",      "https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/120x600_gips/"),
    ("120x600", "hejt",      "https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/120x600_hejt/"),
    ("120x600", "hulajnoga", "https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/120x600_hulajnoga/"),
    ("160x160", "faul",      "https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/160x160_faul/"),
    ("160x160", "gips",      "https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/160x160_gips/"),
    ("160x160", "hejt",      "https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/160x160_hejt/"),
    ("160x160", "hulajnoga", "https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/160x160_hulajnoga/"),
]

results = []

for size, creative, url in URLS:
    expected_bn = EXPECTED.get((size, creative))
    label = f"{size}_{creative}"

    try:
        r = requests.get(url, timeout=15, verify=False)
        html = r.text

        # CLK: var clickTag = "https://track.adform.net/C/?bn=XXXXX;..."
        clk_m = re.search(r'var\s+clickTag\s*=\s*["\']https://track\.adform\.net/C/\?bn=(\d+)', html)
        clk_bn = clk_m.group(1) if clk_m else None

        # IMP: <img src="https://track.adform.net/adfserve/?bn=XXXXX;1x1inv=1;...">
        imp_m = re.search(r'track\.adform\.net/adfserve/\?bn=(\d+);1x1inv=1', html)
        imp_bn = imp_m.group(1) if imp_m else None

        if expected_bn:
            imp_ok = imp_bn == expected_bn
            clk_ok = clk_bn == expected_bn
            status = "PASS" if (imp_ok and clk_ok) else (
                     "IMP_ONLY" if imp_ok else (
                     "CLK_ONLY" if clk_ok else "FAIL"))
            note = ""
        else:
            imp_ok = clk_ok = None
            status = "NO_REF"
            note = f" (160x160 not in Excel)" if size == "160x160" else f" (no 'gips' in Excel; trampolina={TRAMPOLINA.get(size,'?')})"

        results.append({
            "label": label, "size": size, "creative": creative,
            "expected_bn": expected_bn or "—",
            "imp_bn": imp_bn or "MISSING",
            "clk_bn": clk_bn or "MISSING",
            "imp_ok": imp_ok, "clk_ok": clk_ok,
            "status": status, "note": note,
        })

        imp_str = f"{'OK' if imp_ok else ('WRONG' if imp_ok is False else '?')} bn={imp_bn}"
        clk_str = f"{'OK' if clk_ok else ('WRONG' if clk_ok is False else '?')} bn={clk_bn}"
        print(f"[{label}] IMP: {imp_str} | CLK: {clk_str} | expected={expected_bn or '—'} → {status}{note}")

    except Exception as e:
        results.append({"label": label, "size": size, "creative": creative,
                         "expected_bn": expected_bn or "—", "imp_bn": "ERR",
                         "clk_bn": "ERR", "status": "ERROR", "note": str(e)})
        print(f"[{label}] ERROR: {e}")

print("\n" + "=" * 90)
print(f"{'Label':<25} {'Exp BN':<12} {'IMP BN':<12} {'CLK BN':<12} {'Status':<12} Note")
print("-" * 90)
for r in results:
    print(f"{r['label']:<25} {r['expected_bn']:<12} {r['imp_bn']:<12} {r['clk_bn']:<12} {r['status']:<12} {r['note']}")

# Save
out = r"./bankclient_sample_results.txt"
with open(out, "w", encoding="utf-8") as f:
    f.write("THE BANKING CLIENT — Sample HTML banner verification\n\n")
    f.write(f"{'Label':<25} {'Exp BN':<12} {'IMP BN':<12} {'CLK BN':<12} {'Status':<12} Note\n")
    f.write("-" * 90 + "\n")
    for r in results:
        f.write(f"{r['label']:<25} {r['expected_bn']:<12} {r['imp_bn']:<12} {r['clk_bn']:<12} {r['status']:<12} {r['note']}\n")
print(f"\nSaved → {out}")
