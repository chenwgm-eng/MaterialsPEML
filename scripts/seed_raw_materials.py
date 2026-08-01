"""Seed raw_materials.db with example battery materials."""

from __future__ import annotations
from sqlalchemy import text
from battery_materials_agent.db import get_engine

SEED_MATERIALS = [
    ("RM-001", "PEO",     "C(COCCO[*])[*]",                                                                  "BASE_POLYMER", 500.0,  85.0,  "国泰华荣", True,  False, "", "", "", 0.0),
    ("RM-002", "PVDF",    "C(C(F)(F)C(F)(F)[*])[*]",                                                         "BASE_POLYMER", 300.0,  120.0, "索尔维",   True,  False, "", "", "", 0.0),
    ("RM-003", "PAN",     "C(C#[N])([*])[*]",                                                                "BASE_POLYMER", 200.0,  95.0,  "中石化",   True,  False, "", "", "", 0.0),
    ("RM-004", "LiTFSI",  "C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)(F).[Li+]",                                "LITHIUM_SALT", 100.0,  450.0, "多氟多",   True,  False, "", "", "", 0.0),
    ("RM-005", "LiPF6",   "F[P-](F)(F)(F)(F)F.[Li+]",                                                        "LITHIUM_SALT", 800.0,  180.0, "天赐材料", True,  False, "", "", "", 0.0),
    ("RM-006", "LiBF4",   "[B-](F)(F)(F)F.[Li+]",                                                            "LITHIUM_SALT", 150.0,  220.0, "新宙邦",   True,  False, "", "", "", 0.0),
    ("RM-007", "LLZTO",   "[Li+].[Li+].[Li+].[Li+].[Li+].[Li+].[Li+].[Zr+4].[O-2].[O-2].[O-2].[O-2].[O-2].[O-2].[O-2].[Ta]", "FILLER", 50.0, 800.0, "宁德时代", True, False, "", "", "", 0.0),
    ("RM-008", "SiO2",    "O=[Si]=O",                                                                        "FILLER",       1000.0, 15.0,  "赢创",     True,  False, "", "", "", 0.0),
    ("RM-009", "Al2O3",   "O=[Al]O[Al]=O",                                                                    "FILLER",       800.0,  25.0,  "中国铝业", True,  False, "", "", "", 0.0),
    ("RM-010", "LiClO4",  "[Li+].[O-]Cl(=O)=O",                                                              "LITHIUM_SALT", 60.0,   350.0, "国药集团", True,  True,  "", "", "", 0.0),
]


def main() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS industrialization.raw_materials (
                material_id TEXT PRIMARY KEY,
                name TEXT,
                smiles TEXT,
                category TEXT,
                inventory_kg DOUBLE PRECISION,
                cost_per_kg DOUBLE PRECISION,
                supplier TEXT,
                reach_compliant BOOLEAN,
                is_toxic BOOLEAN,
                batch_number TEXT DEFAULT '',
                expiry_date TEXT DEFAULT '',
                coa_uri TEXT DEFAULT '',
                min_order_quantity DOUBLE PRECISION DEFAULT 0.0,
                version BIGINT DEFAULT 1,
                updated_by TEXT DEFAULT '',
                update_reason TEXT DEFAULT '',
                data_source TEXT DEFAULT 'measured',
                prediction_meta JSONB DEFAULT '{}',
                sds_uri TEXT DEFAULT '',
                test_report_uri TEXT DEFAULT '',
                test_institution TEXT DEFAULT '',
                test_date TEXT DEFAULT '',
                properties JSONB DEFAULT '{}'
            )
        """))
        params = [
            {
                "material_id": m[0], "name": m[1], "smiles": m[2], "category": m[3],
                "inventory_kg": m[4], "cost_per_kg": m[5], "supplier": m[6],
                "reach_compliant": m[7], "is_toxic": m[8], "batch_number": m[9],
                "expiry_date": m[10], "coa_uri": m[11], "min_order_quantity": m[12],
            }
            for m in SEED_MATERIALS
        ]
        conn.execute(
            text("""INSERT INTO industrialization.raw_materials
            (material_id, name, smiles, category, inventory_kg, cost_per_kg,
             supplier, reach_compliant, is_toxic,
             batch_number, expiry_date, coa_uri, min_order_quantity)
            VALUES (:material_id, :name, :smiles, :category, :inventory_kg, :cost_per_kg,
                    :supplier, :reach_compliant, :is_toxic,
                    :batch_number, :expiry_date, :coa_uri, :min_order_quantity)
            ON CONFLICT (material_id) DO UPDATE SET
                name=EXCLUDED.name,
                smiles=EXCLUDED.smiles,
                category=EXCLUDED.category,
                inventory_kg=EXCLUDED.inventory_kg,
                cost_per_kg=EXCLUDED.cost_per_kg,
                supplier=EXCLUDED.supplier,
                reach_compliant=EXCLUDED.reach_compliant,
                is_toxic=EXCLUDED.is_toxic,
                batch_number=EXCLUDED.batch_number,
                expiry_date=EXCLUDED.expiry_date,
                coa_uri=EXCLUDED.coa_uri,
                min_order_quantity=EXCLUDED.min_order_quantity"""),
            params,
        )

        count = conn.execute(
            text("SELECT COUNT(*) FROM industrialization.raw_materials")
        ).fetchone()[0]
        print(f"Seeded raw materials into industrialization.raw_materials (total rows: {count})")


if __name__ == "__main__":
    main()
