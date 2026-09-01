"""Direct Adform tag URL verification for Agora moto.pl placements."""
import urllib.request, urllib.error, random

TAGS = [
    ("Agora moto.pl Linia3", 90000001,
     "https://track.adform.net/adfserve/?bn=90000001;1x1inv=1;srctype=3;gdpr=0;gdpr_consent=;ord={ord}",
     "https://track.adform.net/C/?bn=90000001;gdpr=0;gdpr_consent="),
    ("Agora moto.pl Linia4", 90000002,
     "https://track.adform.net/adfserve/?bn=90000002;1x1inv=1;srctype=3;gdpr=0;gdpr_consent=;ord={ord}",
     "https://track.adform.net/C/?bn=90000002;gdpr=0;gdpr_consent="),
]

def check(url):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a): return None
    opener = urllib.request.build_opener(NoRedirect())
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    try:
        with opener.open(url, timeout=10) as r:
            return r.status, len(r.read())
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception as e:
        return None, 0

print("\n" + "="*60)
print("Agora moto.pl -- Adform direct tag validation")
print("="*60)

results = []
for label, bn, imp_url, clk_url in TAGS:
    imp = imp_url.format(ord=random.randint(10000000, 99999999))
    imp_status, imp_size = check(imp)
    clk_status, _        = check(clk_url)
    imp_ok = imp_status in (200, 301, 302, 303)
    clk_ok = clk_status in (200, 301, 302, 303)
    status = "[PASS]" if (imp_ok and clk_ok) else ("[IMP OK/CLK FAIL]" if imp_ok else ("[CLK OK/IMP FAIL]" if clk_ok else "[BOTH FAIL]"))
    print(f"\n  [{label}]  bn={bn}")
    print(f"    IMP  HTTP {imp_status}  {imp_size}b  {'OK' if imp_ok else 'FAIL'}")
    print(f"    CLK  HTTP {clk_status}          {'OK' if clk_ok else 'FAIL'}")
    print(f"    >> {status}")
    results.append((label, bn, status))

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
for label, bn, status in results:
    print(f"  {status:<20} bn={bn}  {label}")
passed = sum(1 for *_, s in results if s == "[PASS]")
print(f"\n{passed}/{len(results)} Adform tags valid")
