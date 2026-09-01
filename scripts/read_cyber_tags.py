import pandas as pd, re

path = r'./data/tags_export.xlsx'
xls = pd.ExcelFile(path)
print("Sheets:", xls.sheet_names)

for sheet in xls.sheet_names:
    df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
    print(f"\n=== {sheet} === cols: {list(df.columns)[:6]}")
    for col in df.columns:
        for i, v in enumerate(df[col].fillna('')):
            s = str(v)
            if 'bn=' in s or '88' in s or 'agora' in s.lower() or 'gazeta' in s.lower() or 'branding' in s.lower() or 'sponsored' in s.lower() or 'artykul' in s.lower():
                print(f"  row {i}, col '{col}': {s[:250]}")
