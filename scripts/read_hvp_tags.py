import pandas as pd, re

df = pd.read_excel(
    r'./data/tags_export.xls',
    engine='xlrd', header=10
)

cols = ['Site', 'Ad ID', 'Ad Name', 'Impression Tag (image)', 'Click Tag']
df2 = df[cols].dropna(subset=['Ad ID'])

for _, row in df2.iterrows():
    site = str(row['Site'])
    name = str(row['Ad Name'])
    ad_id = str(row['Ad ID']).replace('.0','')
    imp = str(row['Impression Tag (image)'])
    clk = str(row['Click Tag'])

    # Extract SRC url from impression tag HTML
    m = re.search(r'SRC=["\']([^"\']+)', imp)
    imp_url = m.group(1) if m else imp[:300]

    print(f"Site={site}  AdID={ad_id}  Name={name}")
    print(f"  IMP_URL: {imp_url[:300]}")
    print(f"  CLK_URL: {clk[:300]}")
    print()
