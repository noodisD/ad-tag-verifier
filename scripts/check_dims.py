import requests, re, warnings
warnings.filterwarnings('ignore')
for url in [
    'https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/160x160_faul/',
    'https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/160x160_hejt/',
    'https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/160x160_gips/',
    'https://tests.sampledata.pl/the banking client_cross_ubezpieczenie_html/160x160_hulajnoga/',
]:
    r = requests.get(url, verify=False, timeout=10)
    html = r.text
    size_meta = re.search(r'ad\.size[^>]*content=["\']([^"\']+)', html)
    title = re.search(r'<title>(.*?)</title>', html)
    dims = re.findall(r'width:(\d+)px.*?height:(\d+)px', html[:2000])
    print(f'URL: {url}')
    print(f'  title: {title.group(1) if title else "?"}')
    print(f'  ad.size meta: {size_meta.group(1) if size_meta else "brak"}')
    if dims:
        print(f'  first w x h in CSS: {dims[0][0]}x{dims[0][1]}')
    print()
