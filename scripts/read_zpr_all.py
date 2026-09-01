import pandas as pd, re

xls = pd.ExcelFile(r'./data/tags_export.xlsx')
print("Sheets:", xls.sheet_names)

for sheet in xls.sheet_names:
    df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
    print(f"\n=== {sheet} === ({len(df)} rows)")
    for col in df.columns:
        for i, v in enumerate(df[col].fillna('')):
            if 'bn=' in str(v) or '88915' in str(v) or '300x600' in str(v) or '300' in str(col):
                print(f"  row {i}, col '{col}': {str(v)[:200]}")
