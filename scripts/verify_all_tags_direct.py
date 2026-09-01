"""Direct CM360 tag URL verification for all Retailclient CDR placements."""
import urllib.request, urllib.error, random, sys

TAGS = [
    ("HVP CB XL1",          900000016,
     "https://ad.doubleclick.net/ddm/trackimp/N1731505.4954855HVP_POL/B90000002.900000031;dc_trk_aid=900000016;dc_trk_cid=900000047;ord={ord};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1?",
     "https://ad.doubleclick.net/ddm/trackclk/N1731505.4954855HVP_POL/B90000002.900000031;dc_trk_aid=900000016;dc_trk_cid=900000047;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1"),
    ("HVP CB XL2",          900000059,
     "https://ad.doubleclick.net/ddm/trackimp/N1731505.4954855HVP_POL/B90000002.900000069;dc_trk_aid=900000059;dc_trk_cid=900000072;ord={ord};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1?",
     "https://ad.doubleclick.net/ddm/trackclk/N1731505.4954855HVP_POL/B90000002.900000069;dc_trk_aid=900000059;dc_trk_cid=900000072;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1"),
    ("Adquery Richmedia",   900000019,
     "https://ad.doubleclick.net/ddm/trackimp/N1731505.5203870ADQUERY0/B90000002.900000066;dc_trk_aid=900000019;dc_trk_cid=900000082;ord={ord};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1?",
     "https://ad.doubleclick.net/ddm/trackclk/N1731505.5203870ADQUERY0/B90000002.900000066;dc_trk_aid=900000019;dc_trk_cid=900000082;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1"),
    ("PushAd",              900000091,
     "https://ad.doubleclick.net/ddm/trackimp/N1731505.3132570PUSHAD0/B90000002.900000107;dc_trk_aid=900000091;dc_trk_cid=900000111;ord={ord};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1?",
     "https://ad.doubleclick.net/ddm/trackclk/N1731505.3132570PUSHAD0/B90000002.900000107;dc_trk_aid=900000091;dc_trk_cid=900000111;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1"),
    ("RASP BIM2",           900000125,
     "https://ad.doubleclick.net/ddm/trackimp/N1731505.5033045RASPPL/B90000002.900000063;dc_trk_aid=900000125;dc_trk_cid=900000130;ord={ord};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1?",
     "https://ad.doubleclick.net/ddm/trackclk/N1731505.5033045RASPPL/B90000002.900000063;dc_trk_aid=900000125;dc_trk_cid=900000130;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1"),
    ("Socialyse Meta CPM",  900000013,
     "https://ad.doubleclick.net/ddm/trackimp/N1731505.1245089SOCIALYSE.COM/B90000002.900000145;dc_trk_aid=900000013;dc_trk_cid=900000044;ord={ord};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1?",
     "https://ad.doubleclick.net/ddm/trackclk/N1731505.1245089SOCIALYSE.COM/B90000002.900000145;dc_trk_aid=900000013;dc_trk_cid=900000044;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1"),
    ("Socialyse Meta RTG",  900000150,
     "https://ad.doubleclick.net/ddm/trackimp/N1731505.1245089SOCIALYSE.COM/B90000002.900000168;dc_trk_aid=900000150;dc_trk_cid=900000174;ord={ord};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1?",
     "https://ad.doubleclick.net/ddm/trackclk/N1731505.1245089SOCIALYSE.COM/B90000002.900000168;dc_trk_aid=900000150;dc_trk_cid=900000174;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1"),
    ("Socialyse TikTok",    900000122,
     "https://ad.doubleclick.net/ddm/trackimp/N1731505.1245089SOCIALYSE.COM/B90000002.900000180;dc_trk_aid=900000122;dc_trk_cid=900000044;ord={ord};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1?",
     "https://ad.doubleclick.net/ddm/trackclk/N1731505.1245089SOCIALYSE.COM/B90000002.900000180;dc_trk_aid=900000122;dc_trk_cid=900000044;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;gdpr=0;gdpr_consent=;ltd=;dc_tdv=1"),
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

print("\n" + "="*65)
print("Retailclient CDR — CM360 direct tag validation (all placements)")
print("="*65)

results = []
for label, aid, imp_url, clk_url in TAGS:
    imp = imp_url.format(ord=random.randint(10000000, 99999999))
    imp_status, imp_size = check(imp)
    clk_status, _        = check(clk_url)
    imp_ok = imp_status in (200, 301, 302, 303)
    clk_ok = clk_status in (200, 301, 302, 303)
    both   = imp_ok and clk_ok
    status = "[PASS]" if both else ("[IMP OK/CLK FAIL]" if imp_ok else ("[CLK OK/IMP FAIL]" if clk_ok else "[BOTH FAIL]"))
    print(f"\n  [{label}]  aid={aid}")
    print(f"    IMP  HTTP {imp_status}  {imp_size}b  {'OK' if imp_ok else 'FAIL'}")
    print(f"    CLK  HTTP {clk_status}          {'OK' if clk_ok else 'FAIL'}")
    print(f"    >> {status}")
    results.append((label, aid, status))

print("\n" + "="*65)
print("SUMMARY")
print("="*65)
for label, aid, status in results:
    print(f"  {status:<25} aid={aid}  {label}")
passed = sum(1 for *_, s in results if s == "[PASS]")
print(f"\n{passed}/{len(results)} placements: both IMP and CLK tags valid")
