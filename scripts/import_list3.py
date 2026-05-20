import pandas as pd
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.activity_code import ActivityCode

# Leer archivo Excel
df = pd.read_excel("list3.xlsx")

# Mostrar columnas detectadas
print("Columnas encontradas:", df.columns.tolist())

# Ajusta estos nombres según tus columnas reales
COLUMN_CODE = df.columns[0]
COLUMN_DESC = df.columns[1]

db: Session = SessionLocal()

inserted = 0
skipped = 0

for _, row in df.iterrows():
    code = str(row[COLUMN_CODE]).strip()
    description = str(row[COLUMN_DESC]).strip() if not pd.isna(row[COLUMN_DESC]) else None

    if not code or code.lower() == "nan":
        continue

    existing = db.query(ActivityCode).filter(ActivityCode.code == code).first()

    if existing:
        skipped += 1
        continue

    new_code = ActivityCode(
        code=code,
        description=description,
        is_active=True
    )

    db.add(new_code)
    inserted += 1

db.commit()
db.close()

print(f"Insertados: {inserted}")
print(f"Omitidos (duplicados): {skipped}")