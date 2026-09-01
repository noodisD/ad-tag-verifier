"""Direct Adform tag validation for all 9 Gazeta.pl Cyberbezpieczenstwo placements."""
import urllib.request, urllib.error, random

BNS = [
    ("Gazeta Samsung 960x1440",       90000001),
    ("Gazeta Samsung 1440x960",       90000002),
    ("Gazeta Samsung 1920x1080",      90000003),
    ("Gazeta Luksusowe 960x1440",     90000004),
    ("Gazeta Luksusowe 1440x960",     90000005),
    ("Gazeta Luksusowe 1920x1080",    90000006),
    ("Gazeta 5200bezryzyka 960x1440", 90000007),
    ("Gazeta 5200bezryzyka 1440x960", 90000008),
    ("Gazeta 5200bezryzyka 1920x1080",90000009),
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
print("Gazeta.pl -- Adform direct tag validation (all 9 placements)")
print("="*60)

results = []
for label, bn in BNS:
    ord_val = random.randint(10000000, 99999999)
    imp_url = f"https://track.adform.net/adfserve/?bn={bn};1x1inv=1;srctype=3;gdpr=0;gdpr_consent=;ord={ord_val}"
    clk_url = f"https://track.adform.net/C/?bn={bn};gdpr=0;gdpr_consent="
    imp_s, imp_sz = check(imp_url)
    clk_s, _      = check(clk_url)
    imp_ok = imp_s in (200, 301, 302, 303)
    clk_ok = clk_s in (200, 301, 302, 303)
    status = "[PASS]" if (imp_ok and clk_ok) else ("[IMP FAIL]" if not imp_ok else "[CLK FAIL]")
    print(f"  bn={bn}  IMP={imp_s}/{imp_sz}b  CLK={clk_s}  {status}  {label}")
    results.append((label, bn, status))

print("\n" + "="*60)
passed = sum(1 for *_, s in results if s == "[PASS]")
print(f"{passed}/{len(results)} Adform tags valid")
