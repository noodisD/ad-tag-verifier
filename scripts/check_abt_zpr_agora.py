import pandas as pd

for path, label in [
    (r'./data/tags_export.xlsx', 'ZPR'),
    (r'./data/tags_export.xlsx', 'Agora'),
]:
    xls = pd.ExcelFile(path)
    found = False
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
        for col in df.columns:
            for i, v in enumerate(df[col].fillna('')):
                if 'abt' in str(v).lower() or 'shield' in str(v).lower():
                    print(f"{label} | {sheet} | row {i} | col '{col}': {str(v)[:200]}")
                    found = True
    if not found:
        print(f"{label}: no ABT Shield mention found in xlsx")
