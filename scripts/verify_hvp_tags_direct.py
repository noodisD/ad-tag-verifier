"""
Direct CM360 tag URL verification for HVP placements.
Hits trackimp and trackclk URLs directly from the XLS.
A valid CM360 tag returns HTTP 200 (pixel) or 302 (redirect).
"""
import urllib.request, urllib.error, re, random, sys

TAGS = [
    ("HVP CB XL1", 900000016,
     "https://ad.doubleclick.net/ddm/trackimp/N1731505.4954855HVP_POL/B90000002.900000031;dc_trk_aid=900000016;dc_trk_cid=900000047;ord={ord};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1?",
     "https://ad.doubleclick.net/ddm/trackclk/N1731505.4954855HVP_POL/B90000002.900000031;dc_trk_aid=900000016;dc_trk_cid=900000047;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1"),
    ("HVP CB XL2", 900000059,
     "https://ad.doubleclick.net/ddm/trackimp/N1731505.4954855HVP_POL/B90000002.900000069;dc_trk_aid=900000059;dc_trk_cid=900000072;ord={ord};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1?",
     "https://ad.doubleclick.net/ddm/trackclk/N1731505.4954855HVP_POL/B90000002.900000069;dc_trk_aid=900000059;dc_trk_cid=900000072;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1"),
]

def check_url(url, follow_redirects=False):
    try:
        if follow_redirects:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.url, len(r.read())
        else:
            # Don't follow redirects — just get the first response
            opener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
            opener.addheaders = [("User-Agent", "Mozilla/5.0")]
            # Use a custom handler that doesn't follow redirects
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            opener2 = urllib.request.build_opener(NoRedirect())
            opener2.addheaders = [("User-Agent", "Mozilla/5.0")]
            try:
                with opener2.open(url, timeout=10) as r:
                    return r.status, r.url, len(r.read())
            except urllib.error.HTTPError as e:
                return e.code, url, 0
    except Exception as e:
        return None, str(e), 0

print("\n" + "="*60)
print("HVP CM360 tag direct verification")
print("="*60)

results = []
for label, aid, imp_url, clk_url in TAGS:
    ord_val = random.randint(10000000, 99999999)
    imp = imp_url.format(ord=ord_val)

    print(f"\n[{label}]  dc_trk_aid={aid}")

    # Impression tag
    status, final_url, size = check_url(imp)
    imp_valid = status in (200, 302, 301, 303)
    print(f"  IMP  HTTP {status}  size={size}b  {'[OK]' if imp_valid else '[FAIL]'}")
    if status in (301, 302, 303):
        print(f"       redirect -> {final_url[:100]}")

    # Click tag
    status2, final_url2, size2 = check_url(clk_url)
    clk_valid = status2 in (200, 302, 301, 303)
    print(f"  CLK  HTTP {status2}  size={size2}b  {'[OK]' if clk_valid else '[FAIL]'}")
    if status2 in (301, 302, 303):
        print(f"       redirect -> {final_url2[:100]}")

    both_ok = imp_valid and clk_valid
    tag_status = "[BOTH TAGS VALID]" if both_ok else ("[IMP only]" if imp_valid else ("[CLK only]" if clk_valid else "[BOTH INVALID]"))
    print(f"  >> {tag_status}")
    results.append((label, aid, imp_valid, clk_valid, tag_status))

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
for label, aid, iv, cv, status in results:
    print(f"  {status}  aid={aid}  {label}")
