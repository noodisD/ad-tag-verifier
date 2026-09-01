import pandas as pd, re

for path, label in [
    (r'./data/tags_export.xlsx', 'AGORA'),
]:
    xls = pd.ExcelFile(path)
    print(f"\n=== {label} sheets: {xls.sheet_names} ===")
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
        print(f"\n  -- {sheet} -- cols: {list(df.columns)}")
        for col in df.columns:
            for i, v in enumerate(df[col].fillna('')):
                if '88' in str(v) or 'bn=' in str(v) or 'linia' in str(v).lower() or 'moto' in str(v).lower():
                    print(f"    row {i}, col '{col}': {str(v)[:250]}")
