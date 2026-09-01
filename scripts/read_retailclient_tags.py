import pandas as pd, re

df = pd.read_excel(
    r'./data/tags_export.xls',
    engine='xlrd', header=10
)

cols = ['Site', 'Ad ID', 'Ad Name', 'Impression Tag (image)', 'Click Tag']
df2 = df[cols].dropna(subset=['Ad ID'])

def get_imp_url(tag):
    m = re.search(r'SRC=["\']([^"\']+)', str(tag))
    return m.group(1) if m else str(tag)[:150]

for _, row in df2.iterrows():
    ad_id = str(row['Ad ID']).replace('.0','')
    imp_url = get_imp_url(row['Impression Tag (image)'])
    clk_url = str(row['Click Tag'])[:150]
    print(f"Site={row['Site']}  AdID={ad_id}")
    print(f"  IMP: {imp_url}")
    print(f"  CLK: {clk_url}")
    print()
