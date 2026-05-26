"""
Read df_complete_186_files.csv in chunks, compute median unit_price per
(sucursal → branch, item), then patch that price into each branch3_*.csv.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BIG_CSV = ROOT / "df_complete_186_files.csv"
COMPLETE_DATA = ROOT / "CompleteData"

SUCURSAL_MAP = {
    "Panem - Punto Valle":        "Punto Valle",
    "Panem - Hotel Kavia":        "Hotel Kavia",
    "Panem - Plaza QIN":          "Plaza QIN",
    "Panem - Hospital Zambrano":  "Hospital Zambrano",
    "Panem - Carreta":            "La Carreta",
    "Panem - La Carreta":         "La Carreta",
    "Panem - Plaza Nativa":       "Plaza Nativa",
    "Panem - Credi Club":         "Credi Club",
}

BRANCH_FILE = {
    "Punto Valle":       "branch3_punto_valle.csv",
    "Hotel Kavia":       "branch3_hotel_kavia.csv",
    "Plaza QIN":         "branch3_plaza_qin.csv",
    "Hospital Zambrano": "branch3_hospital_zambrano.csv",
    "La Carreta":        "branch3_carreta.csv",
    "Plaza Nativa":      "branch3_plaza_nativa.csv",
    "Credi Club":        "branch3_credi_club.csv",
}

print("Leyendo precios del CSV grande en chunks...")
price_frames = []
for chunk in pd.read_csv(
    BIG_CSV,
    usecols=["sucursal", "item", "is_modifier", "unit_price"],
    dtype={"unit_price": float},
    chunksize=200_000,
    low_memory=False,
):
    chunk = chunk[chunk["is_modifier"] == False]
    chunk = chunk[chunk["unit_price"] > 0]
    chunk["branch"] = chunk["sucursal"].map(SUCURSAL_MAP)
    chunk = chunk.dropna(subset=["branch"])
    price_frames.append(chunk[["branch", "item", "unit_price"]])

prices = pd.concat(price_frames, ignore_index=True)
price_map = (
    prices.groupby(["branch", "item"])["unit_price"]
    .median()
    .reset_index()
    .rename(columns={"unit_price": "unit_price_calc"})
)
print(f"  {len(price_map):,} combinaciones (branch, item) con precio")

print("\nParcheando branch3_*.csv...")
for branch, filename in BRANCH_FILE.items():
    path = COMPLETE_DATA / filename
    if not path.exists():
        print(f"  [skip] {filename} no encontrado")
        continue

    df = pd.read_csv(path, low_memory=False)
    df.columns = df.columns.str.strip()
    branch_prices = price_map[price_map["branch"] == branch].set_index("item")["unit_price_calc"]

    df["unit_price"] = df["item"].str.strip().map(branch_prices).fillna(0.0)
    df["revenue"] = df["quantity"] * df["unit_price"]

    df.to_csv(path, index=False)
    matched = (df["unit_price"] > 0).sum()
    total = len(df)
    print(f"  {filename}: {matched:,}/{total:,} filas con precio ({matched/total*100:.1f}%)")

print("\nListo. Vuelve a correr: python -m batch.seed --data-dir CompleteData")
