from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import text

from datetime import datetime, date, timedelta, timezone
import base64
import hashlib
import hmac
import json
import os
import time
import unicodedata
from uuid import uuid4

from database import SessionLocal, Base, engine

from typing import Optional

from models import (
    Product,
    Sale,
    SaleItem,
    SalePayment,
    SaleReturnedContainer,
    SaleLotAllocation,
    StockMovement,
    StockMovementItem,
    StockMovementLotAllocation,
    Purchase,
    PurchaseItem,
    PurchaseInstallment,
    Accounting,
    Formula,
    FormulaItem,
    RawMaterial,
    Settings,
    Supplier,
    Lot,
    Account,
    JournalEntry,
    Journal,
    JournalDetail,
    LotMaterialSourceAllocation
)
from schemas import (
    ProductCreate,
    RawMaterialCreate,
    FormulaCreate,
    FormulaItemCreate,
    SupplierCreate
)

# ================= INIT =================

Base.metadata.create_all(bind=engine)

with engine.connect() as conn:

    conn.execute(
        text(
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS number VARCHAR"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS client VARCHAR"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS date VARCHAR"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS payment_method VARCHAR"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS shipping_cost FLOAT DEFAULT 0"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS amount_paid FLOAT DEFAULT 0"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS balance FLOAT DEFAULT 0"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS payment_status VARCHAR DEFAULT 'PAGADA'"
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sale_payments (
                id SERIAL PRIMARY KEY,
                number VARCHAR UNIQUE,
                sale_id INTEGER REFERENCES sales(id) ON DELETE CASCADE,
                date VARCHAR,
                payment_method VARCHAR,
                amount FLOAT DEFAULT 0,
                notes VARCHAR DEFAULT ''
            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sale_returned_containers (
                id SERIAL PRIMARY KEY,
                sale_id INTEGER REFERENCES sales(id) ON DELETE CASCADE,
                raw_material_id INTEGER REFERENCES raw_materials(id),
                quantity FLOAT DEFAULT 0
            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sale_packaging_items (
                id SERIAL PRIMARY KEY,
                sale_id INTEGER REFERENCES sales(id) ON DELETE CASCADE,
                raw_material_id INTEGER REFERENCES raw_materials(id),
                quantity FLOAT DEFAULT 0,
                unit_cost FLOAT DEFAULT 0,
                subtotal_cost FLOAT DEFAULT 0
            )
            """
        )
    )

    conn.execute(
        text(
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS payment_method VARCHAR"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS product_type VARCHAR DEFAULT 'MANUFACTURED'"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS unit_cost FLOAT DEFAULT 0"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS margin_percent FLOAT DEFAULT 40"
        )
    )

    conn.execute(
        text(
            "UPDATE products SET product_type = 'MANUFACTURED' WHERE product_type IS NULL"
        )
    )

    conn.execute(
        text(
            "UPDATE products SET unit_cost = 0 WHERE unit_cost IS NULL"
        )
    )

    conn.execute(
        text(
            "UPDATE products SET margin_percent = 40 WHERE margin_percent IS NULL"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS product_id INTEGER REFERENCES products(id)"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE formulas ADD COLUMN IF NOT EXISTS margin_percent FLOAT DEFAULT 40"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE formulas ADD COLUMN IF NOT EXISTS output_raw_material_id INTEGER"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE formulas ADD COLUMN IF NOT EXISTS output_type VARCHAR DEFAULT 'PRODUCT'"
        )
    )

    conn.execute(
        text(
            "UPDATE formulas SET output_type = 'PRODUCT' WHERE output_type IS NULL"
        )
    )

    conn.execute(
        text(
            "UPDATE formulas SET margin_percent = 40 WHERE margin_percent IS NULL"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS total FLOAT DEFAULT 0"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS subtotal FLOAT DEFAULT 0"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS cost_total FLOAT DEFAULT 0"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE lots ADD COLUMN IF NOT EXISTS remaining_units FLOAT"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE lots ADD COLUMN IF NOT EXISTS material_cost FLOAT DEFAULT 0"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE lots ADD COLUMN IF NOT EXISTS labor_cost FLOAT DEFAULT 0"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE lots ADD COLUMN IF NOT EXISTS inventory_unit_cost FLOAT"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE lots ADD COLUMN IF NOT EXISTS output_type VARCHAR DEFAULT 'PRODUCT'"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE lots ADD COLUMN IF NOT EXISTS output_raw_material_id INTEGER"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE lots ADD COLUMN IF NOT EXISTS origin VARCHAR DEFAULT 'PRODUCTION'"
        )
    )

    conn.execute(
        text(
            "UPDATE lots SET output_type = 'PRODUCT' WHERE output_type IS NULL"
        )
    )

    conn.execute(
        text(
            "UPDATE lots SET origin = 'PRODUCTION' WHERE origin IS NULL"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS is_intermediate INTEGER DEFAULT 0"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS movement_type VARCHAR DEFAULT 'OUT'"
        )
    )

    conn.execute(
        text(
            "UPDATE stock_movements SET movement_type = 'OUT' WHERE movement_type IS NULL"
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS lot_material_source_allocations (
                id SERIAL PRIMARY KEY,
                consumer_lot_id INTEGER REFERENCES lots(id) ON DELETE CASCADE,
                raw_material_id INTEGER REFERENCES raw_materials(id),
                source_lot_id INTEGER REFERENCES lots(id),
                quantity FLOAT DEFAULT 0,
                unit_cost FLOAT DEFAULT 0,
                subtotal_cost FLOAT DEFAULT 0
            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sale_lot_allocations (

                id SERIAL PRIMARY KEY,

                sale_item_id INTEGER REFERENCES sale_items(id),

                lot_id INTEGER REFERENCES lots(id),

                quantity FLOAT DEFAULT 0,

                unit_cost FLOAT DEFAULT 0,

                subtotal_cost FLOAT DEFAULT 0

            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS lot_materials (

                id SERIAL PRIMARY KEY,

                lot_id INTEGER REFERENCES lots(id) ON DELETE CASCADE,

                raw_material_id INTEGER REFERENCES raw_materials(id),

                quantity FLOAT DEFAULT 0,

                unit_cost FLOAT DEFAULT 0,

                subtotal_cost FLOAT DEFAULT 0,

                source VARCHAR DEFAULT 'REAL'

            )
            """
        )
    )

    conn.execute(
        text(
            "ALTER TABLE lot_materials "
            "ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'REAL'"
        )
    )

    # Los lotes anteriores no guardaban el detalle real de materias primas.
    # Se completa una estimación usando la fórmula actual para que puedan
    # verse en el historial y eliminarse con una advertencia clara.
    conn.execute(
        text(
            """
            INSERT INTO lot_materials (
                lot_id,
                raw_material_id,
                quantity,
                unit_cost,
                subtotal_cost,
                source
            )
            SELECT
                lots.id,
                formula_items.raw_material_id,
                formula_items.quantity,
                COALESCE(raw_materials.cost, 0),
                formula_items.quantity * COALESCE(raw_materials.cost, 0),
                'FORMULA_ESTIMATE'
            FROM lots
            JOIN formula_items
                ON formula_items.formula_id = lots.formula_id
            JOIN raw_materials
                ON raw_materials.id = formula_items.raw_material_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM lot_materials
                WHERE lot_materials.lot_id = lots.id
            )
            """
        )
    )

    conn.execute(
        text(
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS category VARCHAR"
        )
    )
    
    conn.execute(
        text(
        """
             CREATE TABLE IF NOT EXISTS journal_entries (

            id SERIAL PRIMARY KEY,

            date VARCHAR,

            concept VARCHAR,

            account_code VARCHAR,

            account_name VARCHAR,

            debit FLOAT DEFAULT 0,

            credit FLOAT DEFAULT 0

        )
        """
    )
)

    conn.execute(
        text(
            "ALTER TABLE journal_entries "
            "ADD COLUMN IF NOT EXISTS entry_group VARCHAR"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE journal_entries "
            "ADD COLUMN IF NOT EXISTS origin VARCHAR DEFAULT 'MANUAL'"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE journal_entries "
            "ADD COLUMN IF NOT EXISTS origin_id INTEGER"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE journal_entries "
            "ADD COLUMN IF NOT EXISTS entry_number INTEGER"
        )
    )

    conn.execute(
        text(
        """
        CREATE TABLE IF NOT EXISTS journal (

            id SERIAL PRIMARY KEY,

            date VARCHAR,

            concept VARCHAR,

            origin VARCHAR,

            origin_id INTEGER

        )
        """
    )
)


    conn.execute(
        text(
        """
        CREATE TABLE IF NOT EXISTS journal_detail (

            id SERIAL PRIMARY KEY,

            journal_id INTEGER,

            account_id INTEGER,

            debit FLOAT DEFAULT 0,

            credit FLOAT DEFAULT 0

        )
        """
    )
)

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS document_counters (

                document_type VARCHAR PRIMARY KEY,

                last_number INTEGER NOT NULL DEFAULT 0

            )
            """
        )
    )

    conn.execute(
        text(
            """
            INSERT INTO document_counters (
                document_type,
                last_number
            )
            VALUES
                ('LOT', 0),
                ('PURCHASE', 0),
                ('JOURNAL', 0)
            ON CONFLICT (document_type)
            DO NOTHING
            """
        )
    )

    conn.commit()

# ================= PLAN DE CUENTAS =================

def create_default_accounts():

    db = SessionLocal()

    cuentas = [

        {
            "code": "1.1.01",
            "name": "Caja",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.1.02",
            "name": "Banco",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.1.06",
            "name": "Mercado Pago",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.1.04",
            "name": "Cuentas a Cobrar",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.1.05",
            "name": "Tarjetas a cobrar",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.2.01",
            "name": "Materia Prima",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.2.02",
            "name": "Productos Terminados",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.2.03",
            "name": "Mercadería para reventa",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.2.04",
            "name": "Packaging",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.3.01",
            "name": "Materiales",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.3.02",
            "name": "Amort. Acum. Materiales",
            "type": "ACTIVO",
            "category": "REG ACTIVO"
        },

        {
            "code": "1.3.03",
            "name": "Capacitación",
            "type": "ACTIVO",
            "category": "ACTIVO"
        },

        {
            "code": "1.3.04",
            "name": "Amort. Acum. Capacitación",
            "type": "ACTIVO",
            "category": "REG ACTIVO"
        },

        {
            "code": "2.1.01",
            "name": "Proveedores",
            "type": "PASIVO",
            "category": "PASIVO"
        },

        {
            "code": "2.1.02",
            "name": "Sueldos a Pagar",
            "type": "PASIVO",
            "category": "PASIVO"
        },

        {
            "code": "2.1.03",
            "name": "Tarjeta de crédito a pagar",
            "type": "PASIVO",
            "category": "PASIVO"
        },

        {
            "code": "2.1.04",
            "name": "Cuotas de tarjeta a vencer",
            "type": "PASIVO",
            "category": "PASIVO"
        },

        {
            "code": "4.1.01",
            "name": "Ventas",
            "type": "INGRESO",
            "category": "INGRESO"
        },

        {
            "code": "5.1.01",
            "name": "Costo de Ventas",
            "type": "COSTO",
            "category": "COSTO"
        },

        {
            "code": "5.1.14",
            "name": "Packaging utilizado",
            "type": "COSTO",
            "category": "COSTO"
        },

        {
            "code": "5.1.15",
            "name": "Gastos de Sistemas",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.1.16",
            "name": "Costo de mercadería vendida",
            "type": "COSTO",
            "category": "COSTO"
        },

        {
            "code": "5.1.02",
            "name": "Mano de obra",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.1.12",
            "name": "Materiales y gastos de producción",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.1.13",
            "name": "Diferencias de stock",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.1.03",
            "name": "Gastos de testeo",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.1.04",
            "name": "Gastos personales",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.1.07",
            "name": "Regalos",
            "type": "GASTO",
            "category": "GASTO"
        }

    ]


    for cuenta in cuentas:

        existe = db.query(Account).filter(
            Account.code == cuenta["code"]
        ).first()


        if not existe:

            db.add(
                Account(**cuenta)
            )

        # Estas dos cuentas quedaron intercambiadas en una versión anterior.
        # Se restauran por código para no modificar importes ni imputaciones.
        elif cuenta["code"] in {
            "2.1.02",
            "2.1.03"
        }:

            existe.name = cuenta["name"]
            existe.type = cuenta["type"]
            existe.category = cuenta["category"]
            existe.active = 1


    payable_account_names = {
        "2.1.02":
        "Sueldos a Pagar",

        "2.1.03":
        "Tarjeta de crédito a pagar"
    }

    for code, name in payable_account_names.items():

        db.query(JournalEntry).filter(
            JournalEntry.account_code == code
        ).update(
            {
                JournalEntry.account_name:
                name
            },
            synchronize_session=False
        )


    db.commit()

    db.close()




# Migra una sola vez las cuentas que quedaron duplicadas o con códigos
# ocupados por mejoras posteriores. Los importes del diario no se modifican.
def normalize_account_label(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace(".", " ").replace("_", " ")
    return " ".join(value.split())


ACCOUNT_TARGETS = {
    "cuentas a cobrar": ("1.1.04", "Cuentas a Cobrar"),
    "mercado pago": ("1.1.06", "Mercado Pago"),
    "mercaderia para reventa": ("1.2.03", "Mercadería para reventa"),
    "materiales": ("1.3.01", "Materiales"),
    "amort acum materiales": ("1.3.02", "Amort. Acum. Materiales"),
    "capacitacion": ("1.3.03", "Capacitación"),
    "amort acum capacitacion": ("1.3.04", "Amort. Acum. Capacitación"),
    "mano de obra": ("5.1.02", "Mano de obra"),
    "gasto de mano de obra": ("5.1.02", "Mano de obra"),
    "gastos de testeo": ("5.1.03", "Gastos de testeo"),
    "testeo y control de calidad": ("5.1.03", "Gastos de testeo"),
    "gastos personales": ("5.1.04", "Gastos personales"),
    "consumo personal de productos": ("5.1.04", "Gastos personales"),
    "regalos": ("5.1.07", "Regalos"),
    "regalos y obsequios": ("5.1.07", "Regalos"),
    "materiales y gastos de produccion": ("5.1.12", "Materiales y gastos de producción"),
    "diferencias de stock": ("5.1.13", "Diferencias de stock"),
    "packaging utilizado": ("5.1.14", "Packaging utilizado"),
    "gastos de sistemas": ("5.1.15", "Gastos de Sistemas"),
    "costo de mercaderia vendida": ("5.1.16", "Costo de mercadería vendida")
}


def account_target(code, name, origin=None):
    normalized = normalize_account_label(name)
    code = str(code or "").strip()

    if normalized == "packaging":
        if code == "1.2.04":
            return ("1.2.04", "Packaging")
        if code == "5.1.02" or str(origin or "").upper() == "PACKAGING":
            return ("5.1.14", "Packaging utilizado")

    target = ACCOUNT_TARGETS.get(normalized)
    if target:
        return target

    legacy_codes = {
        "1.01.04": ("1.3.02", "Amort. Acum. Materiales"),
        "1.2.05": ("1.3.03", "Capacitación"),
        "1.2.06": ("1.3.04", "Amort. Acum. Capacitación"),
        "5.2.01": ("5.1.02", "Mano de obra"),
        "5.3.01": ("5.1.12", "Materiales y gastos de producción"),
        "5.4.01": ("5.1.13", "Diferencias de stock"),
        "5.4.02": ("5.1.03", "Gastos de testeo"),
        "5.4.03": ("5.1.04", "Gastos personales"),
        "5.4.04": ("5.1.07", "Regalos"),
        "50405": ("5.1.15", "Gastos de Sistemas")
    }
    return legacy_codes.get(code)


def migrate_existing_accounts():
    db = SessionLocal()
    try:
        accounts = db.query(Account).order_by(Account.id.asc()).all()
        records = []
        for account in accounts:
            target = account_target(account.code, account.name)
            records.append((account, str(account.code or ""), target))

        # Libera primero los códigos que van a cambiar para respetar UNIQUE.
        for account, old_code, target in records:
            if target and old_code != target[0]:
                account.code = f"__MIG__{account.id}"
        db.flush()

        for account, old_code, target in records:
            if not target:
                continue
            target_code, target_name = target
            current = db.query(Account).filter(Account.code == target_code).first()
            if current and current.id != account.id:
                db.query(JournalDetail).filter(
                    JournalDetail.account_id == account.id
                ).update(
                    {JournalDetail.account_id: current.id},
                    synchronize_session=False
                )
                db.delete(account)
            else:
                account.code = target_code
                account.name = target_name
                account.active = 1
                db.flush()

        # JournalEntry guarda cuenta como texto: se corrige también el histórico.
        for entry in db.query(JournalEntry).all():
            target = account_target(
                entry.account_code,
                entry.account_name,
                entry.origin
            )
            if target:
                entry.account_code, entry.account_name = target

        db.commit()
    except Exception as error:
        db.rollback()
        print("ERROR MIGRANDO PLAN DE CUENTAS:", error)
    finally:
        db.close()


migrate_existing_accounts()
create_default_accounts()


def infer_journal_origin(
    concept
):

    normalized = str(
        concept or ""
    ).strip().lower()

    if normalized.startswith(
        "packaging venta"
    ):

        return "PACKAGING"

    if normalized.startswith(
        "costo de venta"
    ):

        return "CMV"

    if normalized.startswith(
        "venta "
    ):

        return "VENTA"

    if normalized.startswith(
        "compra "
    ):

        return "COMPRA"

    if normalized.startswith(
        "producción lote"
    ) or normalized.startswith(
        "produccion lote"
    ):

        return "PRODUCCION"

    if normalized.startswith(
        "baja de stock"
    ):

        return "BAJA_STOCK"

    if normalized.startswith(
        "alta de stock"
    ):

        return "ALTA_STOCK"

    if normalized.startswith(
        "cobro venta"
    ):

        return "COBRO_CTA_CTE"

    return "MANUAL"


def initialize_journal_groups():

    db = SessionLocal()

    try:

        entries = (
            db.query(JournalEntry)
            .order_by(JournalEntry.id.asc())
            .all()
        )

        current_key = None

        current_group = None

        for entry in entries:

            if entry.entry_group:

                if not entry.origin:

                    entry.origin = (
                        infer_journal_origin(
                            entry.concept
                        )
                    )

                current_key = None
                current_group = None

                continue

            key = (
                str(entry.date or ""),
                str(entry.concept or "")
            )

            if key != current_key:

                current_key = key

                current_group = str(
                    uuid4()
                )

            entry.entry_group = (
                current_group
            )

            entry.origin = (
                infer_journal_origin(
                    entry.concept
                )
            )

        db.commit()

    except Exception as error:

        db.rollback()

        print(
            "ERROR INICIALIZANDO GRUPOS DE ASIENTOS:",
            error
        )

    finally:

        db.close()


initialize_journal_groups()

def ensure_journal_entry_numbers(db):
    row = db.execute(text(
        "SELECT last_number FROM document_counters WHERE document_type = 'JOURNAL'"
    )).mappings().first()
    counter = int(row["last_number"] if row else 0)

    existing = [
        int(value[0])
        for value in db.query(JournalEntry.entry_number)
        .filter(JournalEntry.entry_number.isnot(None))
        .all()
        if int(value[0]) > 0
    ]
    last_number = max([counter, *existing], default=0)

    groups = db.execute(text(
        """
        SELECT entry_group, MIN(date) AS first_date, MIN(id) AS first_id
        FROM journal_entries
        WHERE entry_number IS NULL
        GROUP BY entry_group
        """
    )).mappings().all()

    first_migration = (last_number == 0)
    groups = sorted(
        groups,
        key=(
            (lambda item: (str(item["first_date"] or ""), int(item["first_id"])))
            if first_migration
            else (lambda item: int(item["first_id"]))
        )
    )

    for group in groups:
        last_number += 1
        db.query(JournalEntry).filter(
            JournalEntry.entry_group == group["entry_group"]
        ).update(
            {JournalEntry.entry_number: last_number},
            synchronize_session=False
        )

    db.execute(text(
        """
        INSERT INTO document_counters (document_type, last_number)
        VALUES ('JOURNAL', :last_number)
        ON CONFLICT (document_type) DO UPDATE SET
        last_number = GREATEST(document_counters.last_number, EXCLUDED.last_number)
        """
    ), {"last_number": last_number})
    db.commit()


def initialize_journal_entry_numbers():
    db = SessionLocal()
    try:
        ensure_journal_entry_numbers(db)
    except Exception as error:
        db.rollback()
        print("ERROR INICIALIZANDO NÚMEROS DE ASIENTO:", error)
    finally:
        db.close()


initialize_journal_entry_numbers()


def get_inventory_unit_cost(
    lot
):

    units = float(
        lot.units_produced or 0
    )

    if units <= 0:

        return 0

    if str(
        getattr(
            lot,
            "output_type",
            "PRODUCT"
        )
        or
        "PRODUCT"
    ).upper() == "RAW_MATERIAL":

        total_cost = float(
            lot.total_cost or 0
        )

        if total_cost > 0:

            return total_cost / units

    material_cost = float(
        lot.material_cost or 0
    )

    if material_cost > 0:

        return (
            material_cost
            /
            units
        )

    return float(
        lot.inventory_unit_cost or 0
    )


def initialize_existing_lot_balances():

    db = SessionLocal()

    try:

        products = db.query(Product).all()

        # ==========================
        # RECONSTRUIR SALDO DE LOTES
        # ==========================

        for product in products:

            product_lots = (
                db.query(Lot)
                .join(
                    Formula,
                    Lot.formula_id == Formula.id
                )
                .filter(
                    Formula.output_product_id == product.id
                )
                .order_by(
                    Lot.production_date.desc(),
                    Lot.id.desc()
                )
                .all()
            )

            if not product_lots:

                continue

            already_initialized = sum(
                max(
                    float(
                        lot.remaining_units or 0
                    ),
                    0
                )
                for lot in product_lots
                if lot.remaining_units is not None
            )

            stock_to_assign = max(
                float(product.stock or 0)
                -
                already_initialized,
                0
            )

            for lot in product_lots:

                if lot.remaining_units is not None:

                    continue

                produced = max(
                    float(
                        lot.units_produced or 0
                    ),
                    0
                )

                assigned = min(
                    produced,
                    stock_to_assign
                )

                lot.remaining_units = assigned

                lot.status = (
                    "Disponible"
                    if assigned > 0
                    else "Agotado"
                )

                stock_to_assign -= assigned

        for lot in db.query(Lot).filter(
            Lot.remaining_units.is_(None)
        ).all():

            lot.remaining_units = 0

            lot.status = "Agotado"


        # ==========================
        # CORREGIR COSTOS DE LOTES
        # ==========================

        settings = db.query(Settings).first()

        labor_hour_cost = float(
            settings.labor_hour_cost
            if settings
            else 10000
        )

        lots = db.query(Lot).all()

        for lot in lots:

            units = float(
                lot.units_produced or 0
            )

            if units <= 0:

                continue

            total_cost = float(
                lot.total_cost or 0
            )

            if total_cost <= 0:

                total_cost = (
                    float(
                        lot.unit_cost or 0
                    )
                    *
                    units
                )

            labor_cost = float(
                lot.labor_cost or 0
            )

            estimated_labor = (
                float(
                    lot.real_labor_hours or 0
                )
                *
                labor_hour_cost
            )

            material_cost = float(
                lot.material_cost or 0
            )

            legacy_cost_needs_split = (

                total_cost > 0

                and

                estimated_labor > 0

                and

                (
                    labor_cost <= 0

                    or

                    material_cost <= 0

                    or

                    abs(
                        material_cost
                        -
                        total_cost
                    )
                    <
                    0.01
                )

            )

            if legacy_cost_needs_split:

                labor_cost = min(
                    estimated_labor,
                    total_cost
                )

                material_cost = max(
                    total_cost
                    -
                    labor_cost,
                    0
                )

            elif material_cost <= 0:

                material_cost = max(
                    total_cost
                    -
                    labor_cost,
                    0
                )

            lot.total_cost = total_cost

            lot.labor_cost = labor_cost

            lot.material_cost = material_cost

            lot.unit_cost = (
                total_cost
                /
                units
            )

            lot.inventory_unit_cost = (
                material_cost
                /
                units
            )


        # ==========================
        # CORREGIR ASIGNACIONES FIFO
        # Y COSTOS INTERNOS DE LAS VENTAS
        # ==========================

        allocations = (
            db.query(SaleLotAllocation).all()
        )

        for allocation in allocations:

            lot = db.query(Lot).filter(
                Lot.id == allocation.lot_id
            ).first()

            if not lot:

                continue

            corrected_unit_cost = (
                get_inventory_unit_cost(
                    lot
                )
            )

            allocation.unit_cost = (
                corrected_unit_cost
            )

            allocation.subtotal_cost = (

                float(
                    allocation.quantity or 0
                )

                *

                corrected_unit_cost

            )

        sale_items = db.query(SaleItem).all()

        for sale_item in sale_items:

            allocations_for_item = (
                db.query(SaleLotAllocation)
                .filter(
                    SaleLotAllocation.sale_item_id
                    ==
                    sale_item.id
                )
                .all()
            )

            if allocations_for_item:

                sale_item.cost_total = sum(

                    float(
                        allocation.subtotal_cost
                        or
                        0
                    )

                    for allocation
                    in allocations_for_item

                )

        # Los asientos contables no se sobrescriben al iniciar.
        # Así se respetan las correcciones manuales realizadas
        # desde el Libro Diario.

        db.commit()

    except Exception as error:

        db.rollback()

        print(
            "ERROR INICIALIZANDO LOTES Y CMV:",
            error
        )

    finally:

        db.close()


initialize_existing_lot_balances()


app = FastAPI(
    title="Nativa ERP",
    version="0.3"
)


# ================= AUTENTICACIÓN =================

ADMIN_USERNAME = os.getenv(
    "ADMIN_USERNAME",
    ""
).strip()

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD",
    ""
)

AUTH_SECRET = os.getenv(
    "AUTH_SECRET",
    ""
)

AUTH_TOKEN_HOURS = int(
    os.getenv(
        "AUTH_TOKEN_HOURS",
        "12"
    )
)

if not ADMIN_USERNAME:

    raise RuntimeError(
        "Falta configurar ADMIN_USERNAME."
    )

if not ADMIN_PASSWORD:

    raise RuntimeError(
        "Falta configurar ADMIN_PASSWORD."
    )

if len(AUTH_SECRET) < 32:

    raise RuntimeError(
        "AUTH_SECRET debe tener al menos 32 caracteres."
    )


def encode_token_part(
    value
):

    return (
        base64.urlsafe_b64encode(
            value
        )
        .rstrip(b"=")
        .decode("utf-8")
    )


def decode_token_part(
    value
):

    padding = (
        "="
        *
        (
            -len(value)
            %
            4
        )
    )

    return base64.urlsafe_b64decode(
        value
        +
        padding
    )


def create_access_token(
    username
):

    now = int(
        time.time()
    )

    payload = {

        "sub":
        username,

        "iat":
        now,

        "exp":
        now
        +
        (
            AUTH_TOKEN_HOURS
            *
            60
            *
            60
        )

    }

    payload_part = encode_token_part(
        json.dumps(
            payload,
            separators=(",", ":")
        ).encode("utf-8")
    )

    signature = hmac.new(
        AUTH_SECRET.encode("utf-8"),
        payload_part.encode("utf-8"),
        hashlib.sha256
    ).digest()

    return (
        payload_part
        +
        "."
        +
        encode_token_part(
            signature
        )
    )


def verify_access_token(
    token
):

    try:

        payload_part, signature_part = (
            token.split(
                ".",
                1
            )
        )

        expected_signature = hmac.new(
            AUTH_SECRET.encode("utf-8"),
            payload_part.encode("utf-8"),
            hashlib.sha256
        ).digest()

        received_signature = (
            decode_token_part(
                signature_part
            )
        )

        if not hmac.compare_digest(
            expected_signature,
            received_signature
        ):

            return None

        payload = json.loads(
            decode_token_part(
                payload_part
            ).decode("utf-8")
        )

        if int(
            payload.get(
                "exp",
                0
            )
        ) < int(
            time.time()
        ):

            return None

        if payload.get(
            "sub"
        ) != ADMIN_USERNAME:

            return None

        return payload

    except Exception:

        return None


PUBLIC_PATHS = {
    "/",
    "/auth/login",
    "/health"
}


@app.middleware("http")
async def protect_api(
    request: Request,
    call_next
):

    if (
        request.method == "OPTIONS"
        or
        request.url.path in PUBLIC_PATHS
    ):

        return await call_next(
            request
        )

    authorization = (
        request.headers.get(
            "Authorization",
            ""
        )
    )

    if not authorization.startswith(
        "Bearer "
    ):

        return JSONResponse(
            status_code=401,
            content={
                "error":
                "Sesión no iniciada"
            }
        )

    token = authorization[
        len("Bearer "):
    ].strip()

    payload = verify_access_token(
        token
    )

    if not payload:

        return JSONResponse(
            status_code=401,
            content={
                "error":
                "La sesión venció o no es válida"
            }
        )

    request.state.username = (
        payload["sub"]
    )

    return await call_next(
        request
    )


cors_origins_value = os.getenv(
    "CORS_ORIGINS",
    (
        "http://localhost:5173,"
        "http://127.0.0.1:5173"
    )
)

cors_origins = [

    origin.strip()

    for origin
    in cors_origins_value.split(",")

    if origin.strip()

]


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=[
        "Authorization",
        "Content-Type"
    ],
)


# ================= MODELOS DE DATOS =================



# ================= DATABASE =================

def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()



def parse_date_value(
    value,
    field_name="fecha",
    allow_none=False
):

    if value in {
        None,
        ""
    }:

        if allow_none:

            return None

        raise ValueError(
            f"La {field_name} es obligatoria"
        )

    if isinstance(
        value,
        datetime
    ):

        return value.date()

    if isinstance(
        value,
        date
    ):

        return value

    try:

        return datetime.strptime(
            str(value)[:10],
            "%Y-%m-%d"
        ).date()

    except Exception as error:

        raise ValueError(
            f"La {field_name} no tiene un formato válido"
        ) from error


# ================= NUMERACIÓN CORRELATIVA =================

def initialize_document_counters():

    db = SessionLocal()

    try:

        numeric_lot_numbers = []

        for lot in db.query(Lot).all():

            value = str(
                lot.lot_number or ""
            ).strip()

            if value.isdigit():

                numeric_lot_numbers.append(
                    int(value)
                )

        numeric_purchase_numbers = []

        for purchase in db.query(Purchase).all():

            value = str(
                purchase.number or ""
            ).strip()

            if value.isdigit():

                numeric_purchase_numbers.append(
                    int(value)
                )

        maximum_lot_number = max(
            numeric_lot_numbers,
            default=0
        )

        maximum_purchase_number = max(
            numeric_purchase_numbers,
            default=0
        )

        db.execute(
            text(
                """
                UPDATE document_counters
                SET last_number = GREATEST(
                    last_number,
                    :maximum
                )
                WHERE document_type = 'LOT'
                """
            ),
            {
                "maximum":
                maximum_lot_number
            }
        )

        db.execute(
            text(
                """
                UPDATE document_counters
                SET last_number = GREATEST(
                    last_number,
                    :maximum
                )
                WHERE document_type = 'PURCHASE'
                """
            ),
            {
                "maximum":
                maximum_purchase_number
            }
        )

        db.commit()

    except Exception as error:

        db.rollback()

        print(
            "ERROR INICIALIZANDO NUMERACIÓN:",
            error
        )

    finally:

        db.close()


initialize_document_counters()


def peek_next_document_number(
    db,
    document_type
):

    row = db.execute(
        text(
            """
            SELECT last_number
            FROM document_counters
            WHERE document_type = :document_type
            """
        ),
        {
            "document_type":
            document_type
        }
    ).mappings().first()

    if not row:

        return 1

    return int(
        row["last_number"]
    ) + 1


def take_next_document_number(
    db,
    document_type
):

    row = db.execute(
        text(
            """
            SELECT last_number
            FROM document_counters
            WHERE document_type = :document_type
            FOR UPDATE
            """
        ),
        {
            "document_type":
            document_type
        }
    ).mappings().first()

    if not row:

        db.execute(
            text(
                """
                INSERT INTO document_counters (
                    document_type,
                    last_number
                )
                VALUES (
                    :document_type,
                    0
                )
                """
            ),
            {
                "document_type":
                document_type
            }
        )

        current_number = 0

    else:

        current_number = int(
            row["last_number"]
        )

    next_number = (
        current_number
        +
        1
    )

    db.execute(
        text(
            """
            UPDATE document_counters
            SET last_number = :next_number
            WHERE document_type = :document_type
            """
        ),
        {
            "next_number":
            next_number,

            "document_type":
            document_type
        }
    )

    return str(
        next_number
    )


@app.get("/next-lot-number")
def next_lot_number(
    db: Session = Depends(get_db)
):

    return {
        "next_number":
        str(
            peek_next_document_number(
                db,
                "LOT"
            )
        )
    }


@app.get("/next-purchase-number")
def next_purchase_number(
    db: Session = Depends(get_db)
):

    return {
        "next_number":
        str(
            peek_next_document_number(
                db,
                "PURCHASE"
            )
        )
    }


# ================= ACCESO =================

@app.post("/auth/login")
def login(
    data: dict
):

    username = str(
        data.get(
            "username",
            ""
        )
    ).strip()

    password = str(
        data.get(
            "password",
            ""
        )
    )

    valid_username = (
        hmac.compare_digest(
            username,
            ADMIN_USERNAME
        )
    )

    valid_password = (
        hmac.compare_digest(
            password,
            ADMIN_PASSWORD
        )
    )

    if not (
        valid_username
        and
        valid_password
    ):

        return JSONResponse(
            status_code=401,
            content={
                "error":
                "Usuario o contraseña incorrectos"
            }
        )

    token = create_access_token(
        ADMIN_USERNAME
    )

    return {

        "access_token":
        token,

        "token_type":
        "bearer",

        "username":
        ADMIN_USERNAME,

        "expires_in_hours":
        AUTH_TOKEN_HOURS

    }


@app.get("/auth/me")
def authenticated_user(
    request: Request
):

    return {
        "username":
        request.state.username
    }


@app.post("/auth/logout")
def logout():

    return {
        "message":
        "Sesión cerrada"
    }


# ================= HOME =================

@app.get("/")
def home():

    return {
        "empresa": "Nativa ERP",
        "version": "0.3",
        "estado": "operativo",
        "acceso": "protegido"
    }


@app.get("/health")
def health():

    return {
        "status":
        "ok"
    }



# ================= PRODUCTOS =================

def normalize_product_type(value):

    normalized = str(
        value or "MANUFACTURED"
    ).strip().upper()

    if normalized in {
        "RESALE",
        "REVENTA",
        "PRODUCTO_REVENTA"
    }:

        return "RESALE"

    return "MANUFACTURED"


def is_resale_product(product):

    return normalize_product_type(
        getattr(
            product,
            "product_type",
            "MANUFACTURED"
        )
    ) == "RESALE"


def suggested_resale_price(
    unit_cost,
    margin_percent
):

    cost = max(
        float(unit_cost or 0),
        0
    )

    margin = float(
        margin_percent or 0
    )

    if margin < 0 or margin >= 100:

        return 0

    denominator = 1 - margin / 100

    if denominator <= 0:

        return 0

    return cost / denominator


@app.get("/products")
def get_products(
    db: Session = Depends(get_db)
):

    products = (
        db.query(Product)
        .filter(
            Product.name
            !=
            "__PRODUCTO_ELIMINADO_HISTORICO__"
        )
        .order_by(Product.name.asc())
        .all()
    )

    result = []

    for product in products:

        product_type = normalize_product_type(
            product.product_type
        )

        if product_type == "RESALE":

            backed_units = float(
                product.stock or 0
            )

            unit_cost = max(
                float(product.unit_cost or 0),
                0
            )

            inventory_value = (
                backed_units
                *
                unit_cost
            )

        else:

            lots = (
                db.query(Lot)
                .join(
                    Formula,
                    Lot.formula_id == Formula.id
                )
                .filter(
                    Formula.output_product_id == product.id,
                    Lot.remaining_units > 0
                )
                .all()
            )

            backed_units = sum(
                float(lot.remaining_units or 0)
                for lot in lots
            )

            inventory_value = sum(
                float(lot.remaining_units or 0)
                *
                get_inventory_unit_cost(lot)
                for lot in lots
            )

            unit_cost = (
                inventory_value / backed_units
                if backed_units > 0
                else 0
            )

        margin_percent = float(
            product.margin_percent or 0
        )

        result.append({
            "id": product.id,
            "name": product.name,
            "price": float(product.price or 0),
            "stock": float(product.stock or 0),
            "product_type": product_type,
            "unit_cost": round(unit_cost, 6),
            "margin_percent": margin_percent,
            "suggested_price": round(
                suggested_resale_price(
                    unit_cost,
                    margin_percent
                ),
                2
            ) if product_type == "RESALE" else 0,
            "inventory_backed_units": round(backed_units, 4),
            "inventory_value": round(inventory_value, 2)
        })

    return result

@app.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db)
):

    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:

        return {
            "error":
            "Producto no encontrado"
        }

    historical_product_name = (
        "__PRODUCTO_ELIMINADO_HISTORICO__"
    )

    if product.name == historical_product_name:

        return {
            "error":
            "El producto histórico interno no puede eliminarse"
        }

    try:

        historical_product = (
            db.query(Product)
            .filter(
                Product.name
                ==
                historical_product_name
            )
            .first()
        )

        if not historical_product:

            historical_product = Product(
                name=historical_product_name,
                price=0,
                stock=0,
                product_type="MANUFACTURED",
                unit_cost=0,
                margin_percent=40
            )

            db.add(historical_product)
            db.flush()

        formula_count = db.query(Formula).filter(
            Formula.output_product_id == product.id
        ).count()

        sale_item_count = db.query(SaleItem).filter(
            SaleItem.product_id == product.id
        ).count()

        stock_movement_item_count = (
            db.query(StockMovementItem)
            .filter(
                StockMovementItem.product_id
                ==
                product.id
            )
            .count()
        )

        purchase_item_count = (
            db.query(PurchaseItem)
            .filter(
                PurchaseItem.product_id
                ==
                product.id
            )
            .count()
        )

        db.query(Formula).filter(
            Formula.output_product_id == product.id
        ).update(
            {
                Formula.output_product_id:
                historical_product.id
            },
            synchronize_session=False
        )

        db.query(SaleItem).filter(
            SaleItem.product_id == product.id
        ).update(
            {
                SaleItem.product_id:
                historical_product.id
            },
            synchronize_session=False
        )

        db.query(StockMovementItem).filter(
            StockMovementItem.product_id == product.id
        ).update(
            {
                StockMovementItem.product_id:
                historical_product.id
            },
            synchronize_session=False
        )

        db.query(PurchaseItem).filter(
            PurchaseItem.product_id == product.id
        ).update(
            {
                PurchaseItem.product_id:
                historical_product.id
            },
            synchronize_session=False
        )

        product_name = product.name

        db.delete(product)
        db.commit()

        detached_records = (
            formula_count
            +
            sale_item_count
            +
            stock_movement_item_count
            +
            purchase_item_count
        )

        return {
            "message":
            f"Producto {product_name} eliminado correctamente",
            "detached_records":
            detached_records,
            "accounting_unchanged":
            True,
            "warning":
            (
                f"Se conservaron {detached_records} registro(s) "
                "histórico(s), reasignados internamente para "
                "permitir la eliminación. Los asientos contables "
                "no fueron modificados."
            )
        }

    except Exception as error:

        db.rollback()

        return JSONResponse(
            status_code=400,
            content={
                "error":
                f"No se pudo eliminar el producto: {error}"
            }
        )



@app.post("/products")
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db)
):

    product_type = normalize_product_type(
        product.product_type
    )

    margin_percent = float(
        product.margin_percent or 0
    )

    if margin_percent < 0 or margin_percent >= 100:

        return JSONResponse(
            status_code=400,
            content={
                "error":
                "El margen debe ser mayor o igual a 0 y menor a 100"
            }
        )

    item = Product(
        name=product.name.strip(),
        price=max(float(product.price or 0), 0),
        stock=max(float(product.stock or 0), 0),
        product_type=product_type,
        unit_cost=(
            max(float(product.unit_cost or 0), 0)
            if product_type == "RESALE"
            else 0
        ),
        margin_percent=margin_percent
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return item

@app.put("/products/{product_id}")
def update_product(
    product_id: int,
    data: dict,
    db: Session = Depends(get_db)
):

    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:

        return {"error": "Producto no encontrado"}

    if "price" in data:

        product.price = max(
            float(data.get("price", 0) or 0),
            0
        )

    if "margin_percent" in data:

        margin_percent = float(
            data.get("margin_percent", 0)
            or
            0
        )

        if margin_percent < 0 or margin_percent >= 100:

            return JSONResponse(
                status_code=400,
                content={
                    "error":
                    "El margen debe ser mayor o igual a 0 y menor a 100"
                }
            )

        product.margin_percent = margin_percent

    db.commit()
    db.refresh(product)

    return product

# ================= VENTAS =================

# ================= VENTAS =================

def is_account_current_method(
    payment_method
):

    normalized = str(
        payment_method or ""
    ).strip().lower()

    return normalized in {
        "cuenta corriente",
        "cta cte",
        "cta. cte.",
        "cta. cte"
    }


def sync_sale_payment_status(
    db,
    sale
):

    payments_total = sum(
        float(payment.amount or 0)
        for payment in db.query(SalePayment).filter(
            SalePayment.sale_id == sale.id
        ).all()
    )

    total = float(sale.total or 0)

    if is_account_current_method(
        sale.payment_method
    ):

        sale.amount_paid = min(
            payments_total,
            total
        )

        sale.balance = max(
            total - payments_total,
            0
        )

        if sale.balance <= 0.000001:

            sale.payment_status = "PAGADA"

        elif payments_total > 0:

            sale.payment_status = "PARCIAL"

        else:

            sale.payment_status = "PENDIENTE"

    else:

        sale.amount_paid = total
        sale.balance = 0
        sale.payment_status = "PAGADA"


def initialize_existing_sale_balances():

    db = SessionLocal()

    try:

        for sale in db.query(Sale).all():

            sync_sale_payment_status(
                db,
                sale
            )

        db.commit()

    except Exception as error:

        db.rollback()

        print(
            "ERROR INICIALIZANDO SALDOS DE VENTAS:",
            error
        )

    finally:

        db.close()


initialize_existing_sale_balances()


@app.post("/sales")
def create_sale(
    data: dict,
    db: Session = Depends(get_db)
):

    count = db.query(Sale).count() + 1

    sale = Sale(

        number=f"F{count:04d}",

        client=data.get(
            "client",
            "Consumidor final"
        ),

        date=data.get(
            "date",
            str(datetime.now())
        ),

        payment_method=data.get(
               "payment_method",
               "Caja"
        ),

        total=0,

        shipping_cost=0,

        amount_paid=0,

        balance=0,

        payment_status=(
            "PENDIENTE"
            if is_account_current_method(
                data.get(
                    "payment_method",
                    "Caja"
                )
            )
            else
            "PAGADA"
        ),

    )

    db.add(sale)

    db.commit()

    db.refresh(sale)

    return {
        "id": sale.id,
        "number": sale.number,
        "payment_method": sale.payment_method
    }

def sale_payment_account(
    payment_method
):

    if is_account_current_method(
        payment_method
    ):

        return (
            "1.1.04",
            "Cuentas a Cobrar"
        )

    normalized_method = str(
        payment_method or ""
    ).strip().lower()

    if normalized_method in {
        "tarjeta de crédito",
        "tarjeta de credito"
    }:

        return (
            "1.1.05",
            "Tarjetas a cobrar"
        )

    if payment_method == "Banco":

        return (
            "1.1.02",
            "Banco"
        )

    if payment_method == "Mercado Pago":

        return (
            "1.1.06",
            "Mercado Pago"
        )

    return (
        "1.1.01",
        "Caja"
    )


def apply_returned_containers(
    db,
    sale,
    containers_data
):

    if (
        containers_data is None
        or
        containers_data == ""
    ):

        return

    if not isinstance(
        containers_data,
        list
    ):

        raise ValueError(
            "Los envases devueltos no tienen un formato válido"
        )

    quantities_by_material = {}

    for item in containers_data:

        raw_material_id = int(
            item.get(
                "raw_material_id"
            )
        )

        quantity = float(
            item.get(
                "quantity",
                0
            )
            or
            0
        )

        if quantity <= 0:

            raise ValueError(
                "La cantidad de envases devueltos debe ser mayor a cero"
            )

        quantities_by_material[raw_material_id] = (
            quantities_by_material.get(
                raw_material_id,
                0
            )
            +
            quantity
        )

    for raw_material_id, quantity in (
        quantities_by_material.items()
    ):

        material = (
            db.query(RawMaterial)
            .filter(
                RawMaterial.id == raw_material_id
            )
            .with_for_update()
            .first()
        )

        if not material:

            raise ValueError(
                "Uno de los envases devueltos no existe en materias primas"
            )

        material.stock = (
            float(material.stock or 0)
            +
            quantity
        )

        db.add(
            SaleReturnedContainer(
                sale_id=sale.id,
                raw_material_id=material.id,
                quantity=quantity
            )
        )


def restore_returned_containers(
    db,
    sale
):

    returned_items = (
        db.query(SaleReturnedContainer)
        .filter(
            SaleReturnedContainer.sale_id
            ==
            sale.id
        )
        .all()
    )

    for returned_item in returned_items:

        material = (
            db.query(RawMaterial)
            .filter(
                RawMaterial.id
                ==
                returned_item.raw_material_id
            )
            .with_for_update()
            .first()
        )

        quantity = float(
            returned_item.quantity or 0
        )

        if material:

            if (
                float(material.stock or 0)
                +
                0.000001
                <
                quantity
            ):

                raise ValueError(
                    f"No se puede revertir la devolución de {material.name}: "
                    "ese stock ya fue utilizado"
                )

            material.stock = (
                float(material.stock or 0)
                -
                quantity
            )

        db.delete(returned_item)


def restore_sale_packaging(
    db,
    sale
):

    rows = db.execute(
        text(
            """
            SELECT
                raw_material_id,
                quantity
            FROM sale_packaging_items
            WHERE sale_id = :sale_id
            """
        ),
        {
            "sale_id":
            sale.id
        }
    ).mappings().all()

    for row in rows:

        material = (
            db.query(RawMaterial)
            .filter(
                RawMaterial.id
                ==
                row["raw_material_id"]
            )
            .with_for_update()
            .first()
        )

        if material:

            material.stock = (
                float(material.stock or 0)
                +
                float(row["quantity"] or 0)
            )

    db.execute(
        text(
            "DELETE FROM sale_packaging_items WHERE sale_id = :sale_id"
        ),
        {
            "sale_id":
            sale.id
        }
    )


def apply_sale_packaging(
    db,
    sale,
    packaging_data
):

    if (
        packaging_data is None
        or
        packaging_data == ""
    ):

        return 0

    if not isinstance(
        packaging_data,
        list
    ):

        raise ValueError(
            "El packaging no tiene un formato válido"
        )

    quantities_by_material = {}

    for item in packaging_data:

        raw_material_id = int(
            item.get(
                "raw_material_id"
            )
        )

        quantity = float(
            item.get(
                "quantity",
                0
            )
            or
            0
        )

        if quantity <= 0:

            raise ValueError(
                "La cantidad de packaging debe ser mayor a cero"
            )

        quantities_by_material[raw_material_id] = (
            quantities_by_material.get(
                raw_material_id,
                0
            )
            +
            quantity
        )

    total_packaging_cost = 0

    for raw_material_id, quantity in (
        quantities_by_material.items()
    ):

        material = (
            db.query(RawMaterial)
            .filter(
                RawMaterial.id == raw_material_id
            )
            .with_for_update()
            .first()
        )

        if not material:

            raise ValueError(
                "Uno de los insumos de packaging no existe"
            )

        if str(
            material.category or ""
        ).strip().lower() != "packaging":

            raise ValueError(
                f"{material.name} no está categorizado como Packaging"
            )

        if (
            float(material.stock or 0)
            +
            0.000001
            <
            quantity
        ):

            raise ValueError(
                (
                    f"Stock insuficiente de {material.name}. "
                    f"Disponible: {float(material.stock or 0):.2f}"
                )
            )

        unit_cost = float(
            material.cost or 0
        )

        subtotal_cost = (
            quantity
            *
            unit_cost
        )

        material.stock = (
            float(material.stock or 0)
            -
            quantity
        )

        db.execute(
            text(
                """
                INSERT INTO sale_packaging_items (
                    sale_id,
                    raw_material_id,
                    quantity,
                    unit_cost,
                    subtotal_cost
                )
                VALUES (
                    :sale_id,
                    :raw_material_id,
                    :quantity,
                    :unit_cost,
                    :subtotal_cost
                )
                """
            ),
            {
                "sale_id":
                sale.id,

                "raw_material_id":
                material.id,

                "quantity":
                quantity,

                "unit_cost":
                unit_cost,

                "subtotal_cost":
                subtotal_cost
            }
        )

        total_packaging_cost += subtotal_cost

    if total_packaging_cost > 0:

        registrar_asiento(
            db=db,
            fecha=sale.date,
            concepto=f"Packaging venta {sale.number}",
            debe_codigo="5.1.14",
            debe_nombre="Packaging utilizado",
            haber_codigo="1.2.01",
            haber_nombre="Materia Prima",
            importe=total_packaging_cost,
            origin="PACKAGING",
            origin_id=sale.id
        )

    return total_packaging_cost


def restore_sale_details(
    db,
    sale
):

    restore_sale_packaging(
        db,
        sale
    )

    restore_returned_containers(
        db,
        sale
    )

    sale_items = db.query(SaleItem).filter(
        SaleItem.sale_id == sale.id
    ).all()

    for item in sale_items:

        allocations = (
            db.query(SaleLotAllocation)
            .filter(
                SaleLotAllocation.sale_item_id
                ==
                item.id
            )
            .all()
        )

        for allocation in allocations:

            lot = db.query(Lot).filter(
                Lot.id == allocation.lot_id
            ).first()

            if lot:

                lot.remaining_units = (
                    float(lot.remaining_units or 0)
                    +
                    float(allocation.quantity or 0)
                )

                lot.status = "Disponible"

            db.delete(allocation)

        product = db.query(Product).filter(
            Product.id == item.product_id
        ).first()

        if product:

            product.stock = (
                float(product.stock or 0)
                +
                float(item.quantity or 0)
            )

        db.delete(item)

    db.query(JournalEntry).filter(
        JournalEntry.origin_id == sale.id,
        JournalEntry.origin.in_([
            "VENTA",
            "CMV",
            "PACKAGING"
        ])
    ).delete(
        synchronize_session=False
    )

    db.query(JournalEntry).filter(
        JournalEntry.origin_id.is_(None),
        JournalEntry.concept.in_([
            f"Venta {sale.number}",
            f"Costo de venta {sale.number}",
            f"Packaging venta {sale.number}"
        ])
    ).delete(
        synchronize_session=False
    )

    sale.total = 0
    sale.shipping_cost = 0

    db.flush()


def apply_sale_items(
    db,
    sale,
    items_data,
    shipping_cost=0,
    returned_containers=None,
    packaging_items=None
):

    shipping_cost_value = float(
        shipping_cost or 0
    )

    if shipping_cost_value < 0:

        raise ValueError(
            "El costo de envío no puede ser negativo"
        )

    if not isinstance(items_data, list) or not items_data:

        raise ValueError(
            "La venta no tiene productos"
        )

    quantities_by_product = {}
    products_by_id = {}
    clean_items = []

    for item in items_data:

        product_id = int(
            item.get("product_id")
        )

        quantity = float(
            item.get("quantity", 0)
            or
            0
        )

        price = float(
            item.get("price", 0)
            or
            0
        )

        if quantity <= 0:

            raise ValueError(
                "Las cantidades deben ser mayores a cero"
            )

        if price < 0:

            raise ValueError(
                "Los precios no pueden ser negativos"
            )

        clean_items.append({
            "product_id": product_id,
            "quantity": quantity,
            "price": price
        })

        quantities_by_product[product_id] = (
            quantities_by_product.get(
                product_id,
                0
            )
            +
            quantity
        )

    for product_id, required_quantity in (
        quantities_by_product.items()
    ):

        product = (
            db.query(Product)
            .filter(
                Product.id == product_id
            )
            .with_for_update()
            .first()
        )

        if not product:

            raise ValueError(
                "Uno de los productos no existe"
            )

        products_by_id[product_id] = product

        if (
            float(product.stock or 0)
            +
            0.000001
            <
            required_quantity
        ):

            raise ValueError(
                f"Stock insuficiente de {product.name}"
            )

        if is_resale_product(product):

            continue

        fifo_lots = (
            db.query(Lot)
            .join(
                Formula,
                Lot.formula_id == Formula.id
            )
            .filter(
                Formula.output_product_id == product_id,
                Lot.remaining_units > 0
            )
            .order_by(
                Lot.production_date.asc(),
                Lot.id.asc()
            )
            .all()
        )

        lot_stock = sum(
            float(lot.remaining_units or 0)
            for lot in fifo_lots
        )

        if (
            lot_stock
            +
            0.000001
            <
            required_quantity
        ):

            raise ValueError(
                (
                    f"El stock de {product.name} no está "
                    "completamente respaldado por lotes. "
                    f"Disponible en lotes: {lot_stock}"
                )
            )

    sale.total = 0
    manufactured_cost = 0
    resale_cost = 0
    zero_cost_lots = []

    for item in clean_items:

        product = products_by_id[
            item["product_id"]
        ]

        quantity = item["quantity"]
        price = item["price"]
        subtotal = quantity * price

        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=quantity,
            price=price,
            subtotal=subtotal,
            cost_total=0
        )

        db.add(sale_item)
        db.flush()

        if is_resale_product(product):

            unit_cost = max(
                float(product.unit_cost or 0),
                0
            )

            item_cost = quantity * unit_cost

            if unit_cost <= 0:

                zero_cost_lots.append(
                    f"Reventa: {product.name}"
                )

            resale_cost += item_cost

        else:

            quantity_to_allocate = quantity
            item_cost = 0

            fifo_lots = (
                db.query(Lot)
                .join(
                    Formula,
                    Lot.formula_id == Formula.id
                )
                .filter(
                    Formula.output_product_id == product.id,
                    Lot.remaining_units > 0
                )
                .order_by(
                    Lot.production_date.asc(),
                    Lot.id.asc()
                )
                .with_for_update()
                .all()
            )

            for lot in fifo_lots:

                available = float(
                    lot.remaining_units or 0
                )

                quantity_used = min(
                    available,
                    quantity_to_allocate
                )

                if quantity_used <= 0:

                    continue

                unit_cost = get_inventory_unit_cost(
                    lot
                )

                subtotal_cost = (
                    quantity_used
                    *
                    unit_cost
                )

                db.add(
                    SaleLotAllocation(
                        sale_item_id=sale_item.id,
                        lot_id=lot.id,
                        quantity=quantity_used,
                        unit_cost=unit_cost,
                        subtotal_cost=subtotal_cost
                    )
                )

                lot.remaining_units = (
                    available
                    -
                    quantity_used
                )

                if lot.remaining_units <= 0.000001:

                    lot.remaining_units = 0
                    lot.status = "Agotado"

                else:

                    lot.status = "Disponible"

                if unit_cost <= 0:

                    zero_cost_lots.append(
                        str(lot.lot_number)
                    )

                item_cost += subtotal_cost
                quantity_to_allocate -= quantity_used

                if quantity_to_allocate <= 0.000001:

                    break

            if quantity_to_allocate > 0.000001:

                raise ValueError(
                    f"No fue posible asignar todos los lotes "
                    f"de {product.name}"
                )

            manufactured_cost += item_cost

        sale_item.cost_total = item_cost

        product.stock = (
            float(product.stock or 0)
            -
            quantity
        )

        sale.total += subtotal

    total_cost_of_sale = (
        manufactured_cost
        +
        resale_cost
    )

    sale.shipping_cost = shipping_cost_value
    sale.total += shipping_cost_value

    apply_returned_containers(
        db,
        sale,
        returned_containers or []
    )

    packaging_cost = apply_sale_packaging(
        db,
        sale,
        packaging_items or []
    )

    payment_code, payment_name = (
        sale_payment_account(
            sale.payment_method
        )
    )

    if sale.total > 0:

        registrar_asiento(
            db=db,
            fecha=sale.date,
            concepto=f"Venta {sale.number}",
            debe_codigo=payment_code,
            debe_nombre=payment_name,
            haber_codigo="4.1.01",
            haber_nombre="Ventas",
            importe=sale.total,
            origin="VENTA",
            origin_id=sale.id
        )

    if manufactured_cost > 0:

        registrar_asiento(
            db=db,
            fecha=sale.date,
            concepto=f"Costo de venta {sale.number}",
            debe_codigo="5.1.01",
            debe_nombre="Costo de Ventas",
            haber_codigo="1.2.02",
            haber_nombre="Productos Terminados",
            importe=manufactured_cost,
            origin="CMV",
            origin_id=sale.id
        )

    if resale_cost > 0:

        registrar_asiento(
            db=db,
            fecha=sale.date,
            concepto=f"Costo de venta {sale.number}",
            debe_codigo="5.1.16",
            debe_nombre="Costo de mercadería vendida",
            haber_codigo="1.2.03",
            haber_nombre="Mercadería para reventa",
            importe=resale_cost,
            origin="CMV",
            origin_id=sale.id
        )

    sync_sale_payment_status(
        db,
        sale
    )

    return (
        total_cost_of_sale,
        packaging_cost,
        zero_cost_lots
    )


@app.post("/sale-items")
def create_sale_items(
    data: dict,
    db: Session = Depends(get_db)
):

    sale = db.query(Sale).filter(
        Sale.id == data.get("sale_id")
    ).first()

    if not sale:

        return {
            "error":
            "Venta no encontrada"
        }

    try:

        total_cost, packaging_cost, zero_cost_lots = (
            apply_sale_items(
                db,
                sale,
                data.get("items", []),
                data.get("shipping_cost", 0),
                data.get("returned_containers", []),
                data.get("packaging_items", [])
            )
        )

        db.commit()

        response = {
            "mensaje":
            "Venta guardada correctamente",
            "costo_productos":
            round(total_cost, 2),

            "costo_packaging":
            round(packaging_cost, 2),

            "costo_venta":
            round(total_cost + packaging_cost, 2)
        }

        if zero_cost_lots:

            response["advertencia"] = (
                "Hay lotes con costo unitario cero: "
                +
                ", ".join(
                    sorted(
                        set(zero_cost_lots)
                    )
                )
            )

        return response

    except Exception as error:

        db.rollback()

        empty_sale = db.query(Sale).filter(
            Sale.id == data.get("sale_id")
        ).first()

        if empty_sale:

            existing_item = db.query(SaleItem).filter(
                SaleItem.sale_id == empty_sale.id
            ).first()

            if not existing_item:

                db.delete(empty_sale)
                db.commit()

        return {
            "error":
            f"No se pudo guardar la venta: {error}"
        }


@app.put("/sales/{sale_id}")
def update_sale(
    sale_id: int,
    data: dict,
    db: Session = Depends(get_db)
):

    sale = db.query(Sale).filter(
        Sale.id == sale_id
    ).first()

    if not sale:

        return {
            "error":
            "Venta no encontrada"
        }

    try:

        requested_payment_method = str(
            data.get(
                "payment_method",
                sale.payment_method
            )
            or
            "Caja"
        ).strip()

        payments_total = sum(
            float(payment.amount or 0)
            for payment in db.query(SalePayment).filter(
                SalePayment.sale_id == sale.id
            ).all()
        )

        if (
            payments_total > 0
            and
            not is_account_current_method(
                requested_payment_method
            )
        ):

            raise ValueError(
                "La venta ya tiene cobros registrados. "
                "Primero eliminá esos cobros antes de cambiar "
                "el medio de pago de cuenta corriente."
            )

        restore_sale_details(
            db,
            sale
        )

        sale.client = str(
            data.get(
                "client",
                "Consumidor final"
            )
            or
            "Consumidor final"
        ).strip()

        sale.date = str(
            data.get(
                "date",
                sale.date
            )
        ).strip()

        sale.payment_method = requested_payment_method

        total_cost, packaging_cost, zero_cost_lots = (
            apply_sale_items(
                db,
                sale,
                data.get("items", []),
                data.get("shipping_cost", 0),
                data.get("returned_containers", []),
                data.get("packaging_items", [])
            )
        )

        if payments_total > float(sale.total or 0) + 0.000001:

            raise ValueError(
                "El nuevo total de la venta es menor que los cobros ya registrados."
            )

        sync_sale_payment_status(
            db,
            sale
        )

        db.commit()

        response = {
            "mensaje":
            f"Venta {sale.number} modificada correctamente",
            "costo_productos":
            round(total_cost, 2),

            "costo_packaging":
            round(packaging_cost, 2),

            "costo_venta":
            round(total_cost + packaging_cost, 2)
        }

        if zero_cost_lots:

            response["advertencia"] = (
                "Hay lotes con costo unitario cero: "
                +
                ", ".join(
                    sorted(
                        set(zero_cost_lots)
                    )
                )
            )

        return response

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo modificar la venta: {error}"
        }


@app.get("/sales")
def get_sales(
    db: Session = Depends(get_db)
):

    sales = (
        db.query(Sale)
        .order_by(
            Sale.date.desc(),
            Sale.id.desc()
        )
        .all()
    )

    sale_items = db.query(SaleItem).all()
    sale_payments = db.query(SalePayment).all()
    sale_returned_items = db.query(SaleReturnedContainer).all()

    sale_packaging_items = db.execute(
        text(
            """
            SELECT
                id,
                sale_id,
                raw_material_id,
                quantity,
                unit_cost,
                subtotal_cost
            FROM sale_packaging_items
            ORDER BY id ASC
            """
        )
    ).mappings().all()

    products = db.query(Product).all()
    raw_materials = db.query(RawMaterial).all()

    product_name_by_id = {
        product.id: product.name
        for product in products
    }

    raw_material_by_id = {
        material.id: material
        for material in raw_materials
    }

    returned_by_sale = {}

    for returned_item in sale_returned_items:

        material = raw_material_by_id.get(
            returned_item.raw_material_id
        )

        returned_by_sale.setdefault(
            returned_item.sale_id,
            []
        ).append({
            "id": returned_item.id,
            "raw_material_id": returned_item.raw_material_id,
            "name": (
                material.name
                if material
                else
                "Envase sin nombre"
            ),
            "unit": (
                material.unit
                if material
                else
                ""
            ),
            "quantity": float(returned_item.quantity or 0)
        })

    items_by_sale = {}

    historical_product_ids = {
        product.id
        for product in products
        if str(product.name or "").strip()
        == "__PRODUCTO_ELIMINADO_HISTORICO__"
    }

    for item in sale_items:
        # FILTRO PRODUCTO HISTORICO EN VENTAS:
        # El registro técnico se conserva en la base, pero no se expone en
        # Historial de Ventas, edición de ventas ni rankings que usan /sales.
        # No se modifica stock, lotes, importes ni contabilidad.
        if item.product_id in historical_product_ids:
            continue

        items_by_sale.setdefault(
            item.sale_id,
            []
        ).append({
            "id": item.id,
            "product_id": item.product_id,
            "name": product_name_by_id.get(
                item.product_id,
                "Producto sin nombre"
            ),
            "quantity": float(item.quantity or 0),
            "price": float(item.price or 0),
            "subtotal": float(item.subtotal or 0),
            "cost_total": float(item.cost_total or 0)
        })

    packaging_by_sale = {}

    for packaging_item in sale_packaging_items:

        material = raw_material_by_id.get(
            packaging_item["raw_material_id"]
        )

        packaging_by_sale.setdefault(
            packaging_item["sale_id"],
            []
        ).append({
            "id": packaging_item["id"],
            "raw_material_id": packaging_item["raw_material_id"],
            "name": (
                material.name
                if material
                else
                "Packaging sin nombre"
            ),
            "unit": (
                material.unit
                if material
                else
                ""
            ),
            "quantity": float(packaging_item["quantity"] or 0),
            "unit_cost": float(packaging_item["unit_cost"] or 0),
            "subtotal_cost": float(packaging_item["subtotal_cost"] or 0)
        })

    payments_by_sale = {}

    for payment in sale_payments:

        payments_by_sale.setdefault(
            payment.sale_id,
            []
        ).append({
            "id": payment.id,
            "number": payment.number,
            "date": payment.date,
            "payment_method": payment.payment_method,
            "amount": float(payment.amount or 0),
            "notes": payment.notes or ""
        })

    result = []

    for sale in sales:

        sync_sale_payment_status(
            db,
            sale
        )

        sale_items_data = items_by_sale.get(
            sale.id,
            []
        )

        sale_packaging_data = packaging_by_sale.get(
            sale.id,
            []
        )

        product_cost = sum(
            float(item.get("cost_total", 0) or 0)
            for item in sale_items_data
        )

        packaging_cost = sum(
            float(item.get("subtotal_cost", 0) or 0)
            for item in sale_packaging_data
        )

        total_real_cost = (
            product_cost
            +
            packaging_cost
        )

        result.append({
            "id": sale.id,
            "number": sale.number,
            "client": sale.client,
            "date": sale.date,
            "payment_method": sale.payment_method,
            "shipping_cost": float(sale.shipping_cost or 0),
            "total": float(sale.total or 0),
            "product_cost": round(product_cost, 2),
            "packaging_cost": round(packaging_cost, 2),
            "total_real_cost": round(total_real_cost, 2),
            "profit": round(
                float(sale.total or 0)
                -
                total_real_cost,
                2
            ),
            "amount_paid": float(sale.amount_paid or 0),
            "balance": float(sale.balance or 0),
            "payment_status": sale.payment_status or "PAGADA",
            "items": sale_items_data,
            "packaging_items": sale_packaging_data,
            "returned_containers": returned_by_sale.get(
                sale.id,
                []
            ),
            "payments": payments_by_sale.get(
                sale.id,
                []
            )
        })

    db.commit()

    return result


@app.get("/accounts-receivable")
def get_accounts_receivable(
    db: Session = Depends(get_db)
):

    sales = (
        db.query(Sale)
        .filter(
            Sale.balance > 0.000001
        )
        .order_by(
            Sale.date.asc(),
            Sale.id.asc()
        )
        .all()
    )

    return [
        {
            "sale_id": sale.id,
            "number": sale.number,
            "client": sale.client,
            "date": sale.date,
            "total": float(sale.total or 0),
            "amount_paid": float(sale.amount_paid or 0),
            "balance": float(sale.balance or 0),
            "payment_status": sale.payment_status or "PENDIENTE"
        }
        for sale in sales
    ]


@app.get("/sales/{sale_id}/payments")
def get_sale_payments(
    sale_id: int,
    db: Session = Depends(get_db)
):

    return [
        {
            "id": payment.id,
            "number": payment.number,
            "sale_id": payment.sale_id,
            "date": payment.date,
            "payment_method": payment.payment_method,
            "amount": float(payment.amount or 0),
            "notes": payment.notes or ""
        }
        for payment in (
            db.query(SalePayment)
            .filter(
                SalePayment.sale_id == sale_id
            )
            .order_by(
                SalePayment.date.asc(),
                SalePayment.id.asc()
            )
            .all()
        )
    ]


@app.post("/sales/{sale_id}/payments")
def create_sale_payment(
    sale_id: int,
    data: dict,
    db: Session = Depends(get_db)
):

    sale = (
        db.query(Sale)
        .filter(
            Sale.id == sale_id
        )
        .with_for_update()
        .first()
    )

    if not sale:

        return {
            "error":
            "Venta no encontrada"
        }

    if not is_account_current_method(
        sale.payment_method
    ):

        return {
            "error":
            "Esta venta no fue registrada en cuenta corriente"
        }

    try:

        amount = float(
            data.get(
                "amount",
                0
            )
            or
            0
        )

        date = str(
            data.get(
                "date",
                str(datetime.now())[:10]
            )
        ).strip()

        payment_method = str(
            data.get(
                "payment_method",
                "Caja"
            )
            or
            "Caja"
        ).strip()

        notes = str(
            data.get(
                "notes",
                ""
            )
            or
            ""
        ).strip()

        sync_sale_payment_status(
            db,
            sale
        )

        if amount <= 0:

            raise ValueError(
                "El importe debe ser mayor a cero"
            )

        if is_account_current_method(
            payment_method
        ):

            raise ValueError(
                "Elegí el medio real con el que se recibió el cobro"
            )

        if amount > float(sale.balance or 0) + 0.000001:

            raise ValueError(
                "El cobro supera el saldo pendiente de la venta"
            )

        payment = SalePayment(
            number=None,
            sale_id=sale.id,
            date=date,
            payment_method=payment_method,
            amount=amount,
            notes=notes
        )

        db.add(payment)
        db.flush()

        payment.number = f"CC{payment.id:04d}"

        payment_code, payment_name = (
            sale_payment_account(
                payment_method
            )
        )

        registrar_asiento(
            db=db,
            fecha=date,
            concepto=f"Cobro venta {sale.number} - {payment.number}",
            debe_codigo=payment_code,
            debe_nombre=payment_name,
            haber_codigo="1.1.04",
            haber_nombre="Cuentas a Cobrar",
            importe=amount,
            origin="COBRO_CTA_CTE",
            origin_id=payment.id
        )

        sync_sale_payment_status(
            db,
            sale
        )

        db.commit()
        db.refresh(payment)

        return {
            "id": payment.id,
            "number": payment.number,
            "message": "Cobro registrado correctamente",
            "amount_paid": round(
                float(sale.amount_paid or 0),
                2
            ),
            "balance": round(
                float(sale.balance or 0),
                2
            ),
            "payment_status": sale.payment_status
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo registrar el cobro: {error}"
        }


@app.delete("/sale-payments/{payment_id}")
def delete_sale_payment(
    payment_id: int,
    db: Session = Depends(get_db)
):

    payment = db.query(SalePayment).filter(
        SalePayment.id == payment_id
    ).first()

    if not payment:

        return {
            "error":
            "Cobro no encontrado"
        }

    sale = db.query(Sale).filter(
        Sale.id == payment.sale_id
    ).first()

    try:

        db.query(JournalEntry).filter(
            JournalEntry.origin == "COBRO_CTA_CTE",
            JournalEntry.origin_id == payment.id
        ).delete(
            synchronize_session=False
        )

        db.delete(payment)
        db.flush()

        if sale:

            sync_sale_payment_status(
                db,
                sale
            )

        db.commit()

        return {
            "message":
            "Cobro eliminado correctamente"
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo eliminar el cobro: {error}"
        }


def reverse_and_delete_sale(
    db,
    sale
):

    payments = db.query(SalePayment).filter(
        SalePayment.sale_id == sale.id
    ).all()

    for payment in payments:

        db.query(JournalEntry).filter(
            JournalEntry.origin == "COBRO_CTA_CTE",
            JournalEntry.origin_id == payment.id
        ).delete(
            synchronize_session=False
        )

        db.delete(payment)

    restore_sale_details(
        db,
        sale
    )

    db.delete(sale)


@app.delete("/sales")
def delete_sales(
    db: Session = Depends(get_db)
):

    sales = db.query(Sale).all()

    for sale in sales:

        reverse_and_delete_sale(
            db,
            sale
        )

    db.commit()

    return {
        "mensaje":
        "Ventas eliminadas correctamente"
    }


@app.delete("/sales/{sale_id}")
def delete_sale(
    sale_id: int,
    db: Session = Depends(get_db)
):

    sale = db.query(Sale).filter(
        Sale.id == sale_id
    ).first()

    if not sale:

        return {
            "error":
            "Venta no encontrada"
        }

    reverse_and_delete_sale(
        db,
        sale
    )

    db.commit()

    return {
        "mensaje":
        "Venta eliminada correctamente"
    }



# ================= BAJAS DE STOCK =================

STOCK_MOVEMENT_REASONS = {

    "STOCK_CONTROL": {
        "label":
        "Control de stock",

        "account_code":
        "5.1.13",

        "account_name":
        "Diferencias de stock"
    },

    "LOT_TEST": {
        "label":
        "Testeo de lote",

        "account_code":
        "5.1.03",

        "account_name":
        "Gastos de testeo"
    },

    "PERSONAL_USE": {
        "label":
        "Consumo personal",

        "account_code":
        "5.1.04",

        "account_name":
        "Gastos personales"
    },

    "GIFT": {
        "label":
        "Regalo u obsequio",

        "account_code":
        "5.1.07",

        "account_name":
        "Regalos"
    }

}


def latest_formula_for_product(
    db,
    product_id
):

    return (
        db.query(Formula)
        .filter(
            Formula.output_product_id == product_id
        )
        .order_by(
            Formula.id.desc()
        )
        .first()
    )


def latest_product_inventory_cost(
    db,
    product_id
):

    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if product and is_resale_product(product):

        return max(
            float(product.unit_cost or 0),
            0
        )

    lots = (
        db.query(Lot)
        .join(
            Formula,
            Lot.formula_id == Formula.id
        )
        .filter(
            Formula.output_product_id == product_id
        )
        .order_by(
            Lot.production_date.desc(),
            Lot.id.desc()
        )
        .all()
    )

    for lot in lots:

        unit_cost = get_inventory_unit_cost(
            lot
        )

        if unit_cost > 0:

            return unit_cost

    return 0


def create_positive_adjustment_lot(
    db,
    product,
    quantity,
    date,
    movement_number,
    notes
):

    formula = latest_formula_for_product(
        db,
        product.id
    )

    if not formula:

        raise ValueError(
            f"{product.name} no tiene una fórmula asociada para respaldar el alta."
        )

    unit_cost = latest_product_inventory_cost(
        db,
        product.id
    )

    total_cost = quantity * unit_cost

    lot = Lot(
        lot_number=take_next_document_number(
            db,
            "LOT"
        ),
        formula_id=formula.id,
        output_type="PRODUCT",
        output_raw_material_id=None,
        origin="STOCK_ADJUSTMENT",
        production_date=parse_date_value(
            date,
            "fecha del ajuste"
        ),
        expiration_date=None,
        units_produced=quantity,
        remaining_units=quantity,
        real_labor_hours=0,
        material_cost=total_cost,
        labor_cost=0,
        total_cost=total_cost,
        unit_cost=unit_cost,
        inventory_unit_cost=unit_cost,
        notes=(
            f"Alta por control de stock {movement_number}. "
            f"{notes}"
        ).strip(),
        status="Disponible"
    )

    db.add(lot)
    db.flush()

    return lot, total_cost


@app.post("/stock-movements")
def create_stock_movement(
    data: dict,
    db: Session = Depends(get_db)
):

    date = str(data.get("date", "")).strip()
    reason = str(data.get("reason", "")).strip().upper()
    movement_type = str(
        data.get(
            "movement_type",
            data.get("type", "OUT")
        )
        or
        "OUT"
    ).strip().upper()
    notes = str(data.get("notes", "")).strip()
    items_data = data.get("items", [])

    if movement_type in {
        "ALTA",
        "IN",
        "ENTRADA",
        "POSITIVE"
    }:

        movement_type = "IN"

    else:

        movement_type = "OUT"

    if not date:

        return {"error": "La fecha es obligatoria"}

    reason_data = STOCK_MOVEMENT_REASONS.get(reason)

    if not reason_data:

        return {"error": "El motivo del ajuste no es válido"}

    if movement_type == "IN" and reason != "STOCK_CONTROL":

        return {
            "error":
            "Las altas solo pueden registrarse por control de stock"
        }

    if not isinstance(items_data, list) or not items_data:

        return {"error": "Agregá al menos un producto"}

    quantities_by_product = {}

    for item in items_data:

        try:

            product_id = int(item.get("product_id"))
            quantity = float(item.get("quantity", 0) or 0)

        except (TypeError, ValueError):

            return {
                "error":
                "Hay un producto o una cantidad inválida"
            }

        if quantity <= 0:

            return {
                "error":
                "Las cantidades deben ser mayores a cero"
            }

        quantities_by_product[product_id] = (
            quantities_by_product.get(product_id, 0)
            +
            quantity
        )

    products_by_id = {}

    for product_id, required_quantity in (
        quantities_by_product.items()
    ):

        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .with_for_update()
            .first()
        )

        if not product:

            return {
                "error":
                "Uno de los productos no existe"
            }

        products_by_id[product_id] = product

        if movement_type == "IN":

            if (
                not is_resale_product(product)
                and
                not latest_formula_for_product(db, product_id)
            ):

                return {
                    "error":
                    (
                        f"{product.name} no tiene una fórmula asociada. "
                        "No se puede crear un lote de ajuste seguro."
                    )
                }

            continue

        if (
            float(product.stock or 0)
            +
            0.000001
            <
            required_quantity
        ):

            return {
                "error":
                f"Stock insuficiente de {product.name}"
            }

        if is_resale_product(product):

            continue

        fifo_lots = (
            db.query(Lot)
            .join(Formula, Lot.formula_id == Formula.id)
            .filter(
                Formula.output_product_id == product_id,
                Lot.remaining_units > 0
            )
            .order_by(
                Lot.production_date.asc(),
                Lot.id.asc()
            )
            .all()
        )

        lot_stock = sum(
            float(lot.remaining_units or 0)
            for lot in fifo_lots
        )

        if lot_stock + 0.000001 < required_quantity:

            return {
                "error":
                (
                    f"El stock de {product.name} no está "
                    "completamente respaldado por lotes. "
                    f"Disponible en lotes: {lot_stock}"
                )
            }

    movement = StockMovement(
        number=None,
        date=date,
        reason=reason,
        movement_type=movement_type,
        notes=notes,
        total_cost=0
    )

    try:

        db.add(movement)
        db.flush()

        prefix = "AS" if movement_type == "IN" else "BS"
        movement.number = f"{prefix}{movement.id:04d}"

        manufactured_cost = 0
        resale_cost = 0
        zero_cost_lots = []

        for product_id, quantity in (
            quantities_by_product.items()
        ):

            product = products_by_id[product_id]

            movement_item = StockMovementItem(
                stock_movement_id=movement.id,
                product_id=product.id,
                quantity=quantity,
                cost_total=0
            )

            db.add(movement_item)
            db.flush()

            if is_resale_product(product):

                unit_cost = max(
                    float(product.unit_cost or 0),
                    0
                )
                item_cost = quantity * unit_cost
                movement_item.cost_total = item_cost

                if movement_type == "IN":

                    product.stock = (
                        float(product.stock or 0)
                        +
                        quantity
                    )

                else:

                    product.stock = (
                        float(product.stock or 0)
                        -
                        quantity
                    )

                resale_cost += item_cost

                if unit_cost <= 0:

                    zero_cost_lots.append(
                        f"Reventa: {product.name}"
                    )

                continue

            if movement_type == "IN":

                adjustment_lot, item_cost = (
                    create_positive_adjustment_lot(
                        db=db,
                        product=product,
                        quantity=quantity,
                        date=date,
                        movement_number=movement.number,
                        notes=notes
                    )
                )

                db.add(
                    StockMovementLotAllocation(
                        stock_movement_item_id=movement_item.id,
                        lot_id=adjustment_lot.id,
                        quantity=quantity,
                        unit_cost=get_inventory_unit_cost(
                            adjustment_lot
                        ),
                        subtotal_cost=item_cost
                    )
                )

                movement_item.cost_total = item_cost
                product.stock = (
                    float(product.stock or 0)
                    +
                    quantity
                )
                manufactured_cost += item_cost

                if item_cost <= 0:

                    zero_cost_lots.append(
                        str(adjustment_lot.lot_number)
                    )

                continue

            quantity_to_allocate = quantity
            item_cost = 0

            fifo_lots = (
                db.query(Lot)
                .join(Formula, Lot.formula_id == Formula.id)
                .filter(
                    Formula.output_product_id == product.id,
                    Lot.remaining_units > 0
                )
                .order_by(
                    Lot.production_date.asc(),
                    Lot.id.asc()
                )
                .with_for_update()
                .all()
            )

            for lot in fifo_lots:

                available = float(lot.remaining_units or 0)
                quantity_used = min(
                    available,
                    quantity_to_allocate
                )

                if quantity_used <= 0:

                    continue

                unit_cost = get_inventory_unit_cost(lot)
                subtotal_cost = quantity_used * unit_cost

                db.add(
                    StockMovementLotAllocation(
                        stock_movement_item_id=movement_item.id,
                        lot_id=lot.id,
                        quantity=quantity_used,
                        unit_cost=unit_cost,
                        subtotal_cost=subtotal_cost
                    )
                )

                lot.remaining_units = available - quantity_used

                if lot.remaining_units <= 0.000001:

                    lot.remaining_units = 0
                    lot.status = "Agotado"

                else:

                    lot.status = "Disponible"

                if unit_cost <= 0:

                    zero_cost_lots.append(str(lot.lot_number))

                item_cost += subtotal_cost
                quantity_to_allocate -= quantity_used

                if quantity_to_allocate <= 0.000001:

                    break

            if quantity_to_allocate > 0.000001:

                raise ValueError(
                    f"No fue posible asignar todos los lotes de {product.name}"
                )

            movement_item.cost_total = item_cost
            product.stock = (
                float(product.stock or 0)
                -
                quantity
            )
            manufactured_cost += item_cost

        total_cost = manufactured_cost + resale_cost
        movement.total_cost = total_cost

        action_concept = (
            f"Alta de stock {movement.number} - "
            if movement_type == "IN"
            else f"Baja de stock {movement.number} - "
        ) + reason_data["label"]

        origin = (
            "ALTA_STOCK"
            if movement_type == "IN"
            else "BAJA_STOCK"
        )

        if manufactured_cost > 0:

            if movement_type == "IN":

                registrar_asiento(
                    db=db,
                    fecha=date,
                    concepto=action_concept,
                    debe_codigo="1.2.02",
                    debe_nombre="Productos Terminados",
                    haber_codigo=reason_data["account_code"],
                    haber_nombre=reason_data["account_name"],
                    importe=manufactured_cost,
                    origin=origin,
                    origin_id=movement.id
                )

            else:

                registrar_asiento(
                    db=db,
                    fecha=date,
                    concepto=action_concept,
                    debe_codigo=reason_data["account_code"],
                    debe_nombre=reason_data["account_name"],
                    haber_codigo="1.2.02",
                    haber_nombre="Productos Terminados",
                    importe=manufactured_cost,
                    origin=origin,
                    origin_id=movement.id
                )

        if resale_cost > 0:

            if movement_type == "IN":

                registrar_asiento(
                    db=db,
                    fecha=date,
                    concepto=action_concept,
                    debe_codigo="1.2.03",
                    debe_nombre="Mercadería para reventa",
                    haber_codigo=reason_data["account_code"],
                    haber_nombre=reason_data["account_name"],
                    importe=resale_cost,
                    origin=origin,
                    origin_id=movement.id
                )

            else:

                registrar_asiento(
                    db=db,
                    fecha=date,
                    concepto=action_concept,
                    debe_codigo=reason_data["account_code"],
                    debe_nombre=reason_data["account_name"],
                    haber_codigo="1.2.03",
                    haber_nombre="Mercadería para reventa",
                    importe=resale_cost,
                    origin=origin,
                    origin_id=movement.id
                )

        db.commit()
        db.refresh(movement)

        action_label = "Alta" if movement_type == "IN" else "Baja"

        response = {
            "id": movement.id,
            "number": movement.number,
            "movement_type": movement_type,
            "message": f"{action_label} de stock guardada correctamente",
            "total_cost": round(total_cost, 2)
        }

        if zero_cost_lots:

            response["advertencia"] = (
                "Hay artículos con costo unitario cero: "
                +
                ", ".join(sorted(set(zero_cost_lots)))
            )

        return response

    except Exception as error:

        db.rollback()
        action_label = "alta" if movement_type == "IN" else "baja"

        return {
            "error":
            f"No se pudo guardar la {action_label} de stock: {error}"
        }


@app.get("/stock-movements")
def get_stock_movements(
    db: Session = Depends(get_db)
):

    movements = (
        db.query(StockMovement)
        .order_by(
            StockMovement.date.desc(),
            StockMovement.id.desc()
        )
        .all()
    )

    movement_items = db.query(
        StockMovementItem
    ).all()

    products = db.query(Product).all()

    product_name_by_id = {
        product.id: product.name
        for product in products
    }

    items_by_movement = {}

    for item in movement_items:

        items_by_movement.setdefault(
            item.stock_movement_id,
            []
        ).append({
            "id": item.id,
            "product_id": item.product_id,
            "name": product_name_by_id.get(
                item.product_id,
                "Producto sin nombre"
            ),
            "quantity": float(item.quantity or 0),
            "cost_total": float(item.cost_total or 0)
        })

    return [
        {
            "id": movement.id,
            "number": movement.number,
            "date": movement.date,
            "movement_type": (
                movement.movement_type
                or
                "OUT"
            ),
            "movement_label": (
                "Alta"
                if (movement.movement_type or "OUT") == "IN"
                else
                "Baja"
            ),
            "reason": movement.reason,
            "reason_label": STOCK_MOVEMENT_REASONS.get(
                movement.reason,
                {}
            ).get(
                "label",
                movement.reason
            ),
            "notes": movement.notes or "",
            "total_cost": float(movement.total_cost or 0),
            "items": items_by_movement.get(
                movement.id,
                []
            )
        }
        for movement in movements
    ]


@app.delete("/stock-movements/{movement_id}")
def delete_stock_movement(
    movement_id: int,
    db: Session = Depends(get_db)
):

    movement = db.query(StockMovement).filter(
        StockMovement.id == movement_id
    ).first()

    if not movement:

        return {
            "error":
            "Ajuste de stock no encontrado"
        }

    movement_type = movement.movement_type or "OUT"

    try:

        movement_items = (
            db.query(StockMovementItem)
            .filter(
                StockMovementItem.stock_movement_id == movement.id
            )
            .all()
        )

        if movement_type == "IN":

            validations = []

            for item in movement_items:

                product = db.query(Product).filter(
                    Product.id == item.product_id
                ).first()

                if not product:

                    raise ValueError(
                        "No se encontró uno de los productos del ajuste"
                    )

                if (
                    float(product.stock or 0)
                    +
                    0.000001
                    <
                    float(item.quantity or 0)
                ):

                    raise ValueError(
                        f"No se puede revertir el alta porque el stock actual de {product.name} es menor."
                    )

                allocations = (
                    db.query(StockMovementLotAllocation)
                    .filter(
                        StockMovementLotAllocation.stock_movement_item_id == item.id
                    )
                    .all()
                )

                if is_resale_product(product):

                    validations.append((item, product, None, None))
                    continue

                for allocation in allocations:

                    lot = db.query(Lot).filter(
                        Lot.id == allocation.lot_id
                    ).first()

                    if not lot:

                        raise ValueError(
                            "No se encontró el lote creado por el alta"
                        )

                    if lot.origin != "STOCK_ADJUSTMENT":

                        raise ValueError(
                            "El lote del alta no puede eliminarse automáticamente"
                        )

                    if (
                        float(lot.remaining_units or 0)
                        +
                        0.000001
                        <
                        float(allocation.quantity or 0)
                    ):

                        raise ValueError(
                            (
                                f"El lote {lot.lot_number} ya fue utilizado. "
                                "No se puede eliminar esta alta."
                            )
                        )

                    validations.append(
                        (item, product, allocation, lot)
                    )

            processed_items = set()

            for item, product, allocation, lot in validations:

                if item.id not in processed_items:

                    product.stock = (
                        float(product.stock or 0)
                        -
                        float(item.quantity or 0)
                    )
                    processed_items.add(item.id)

                if allocation:

                    db.delete(allocation)

                if lot:

                    db.delete(lot)

            for item in movement_items:

                db.delete(item)

            origin = "ALTA_STOCK"
            action_label = "Alta"

        else:

            for item in movement_items:

                allocations = (
                    db.query(StockMovementLotAllocation)
                    .filter(
                        StockMovementLotAllocation.stock_movement_item_id == item.id
                    )
                    .all()
                )

                for allocation in allocations:

                    lot = db.query(Lot).filter(
                        Lot.id == allocation.lot_id
                    ).first()

                    if lot:

                        lot.remaining_units = (
                            float(lot.remaining_units or 0)
                            +
                            float(allocation.quantity or 0)
                        )
                        lot.status = "Disponible"

                    db.delete(allocation)

                product = db.query(Product).filter(
                    Product.id == item.product_id
                ).first()

                if product:

                    product.stock = (
                        float(product.stock or 0)
                        +
                        float(item.quantity or 0)
                    )

                db.delete(item)

            origin = "BAJA_STOCK"
            action_label = "Baja"

        db.query(JournalEntry).filter(
            JournalEntry.origin == origin,
            JournalEntry.origin_id == movement.id
        ).delete(synchronize_session=False)

        db.query(JournalEntry).filter(
            JournalEntry.origin_id.is_(None),
            JournalEntry.concept.like(
                f"{action_label} de stock {movement.number}%"
            )
        ).delete(synchronize_session=False)

        db.delete(movement)
        db.commit()

        return {
            "message":
            f"{action_label} de stock {movement.number} eliminada correctamente"
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo eliminar el ajuste de stock: {error}"
        }


# ================= COMPRAS =================

# ================= COMPRAS =================

@app.get("/purchases")
def get_purchases(
    db: Session = Depends(get_db)
):

    purchases = (
        db.query(Purchase)
        .order_by(
            Purchase.date.desc(),
            Purchase.id.desc()
        )
        .all()
    )

    purchase_items = db.query(PurchaseItem).all()
    purchase_installments = db.query(PurchaseInstallment).all()
    raw_materials = db.query(RawMaterial).all()
    products = db.query(Product).all()
    suppliers = db.query(Supplier).all()

    material_by_id = {
        material.id: material
        for material in raw_materials
    }

    product_by_id = {
        product.id: product
        for product in products
    }

    supplier_name_by_id = {
        str(supplier.id): supplier.name
        for supplier in suppliers
    }

    supplier_name_by_name = {
        str(supplier.name).strip().lower(): supplier.name
        for supplier in suppliers
        if supplier.name
    }

    items_by_purchase = {}

    for item in purchase_items:

        if item.product_id:

            product = product_by_id.get(item.product_id)

            item_data = {
                "id": item.id,
                "item_type": "RESALE",
                "raw_material_id": None,
                "product_id": item.product_id,
                "name": (
                    product.name
                    if product
                    else "Producto de reventa sin nombre"
                ),
                "unit": "unidad",
                "quantity": float(item.quantity or 0),
                "price": float(item.price or 0)
            }

        else:

            material = material_by_id.get(
                item.raw_material_id
            )

            item_data = {
                "id": item.id,
                "item_type": "RAW_MATERIAL",
                "raw_material_id": item.raw_material_id,
                "product_id": None,
                "name": (
                    material.name
                    if material
                    else "Materia prima sin nombre"
                ),
                "unit": material.unit if material else "",
                "quantity": float(item.quantity or 0),
                "price": float(item.price or 0)
            }

        items_by_purchase.setdefault(
            item.purchase_id,
            []
        ).append(item_data)

    installments_by_purchase = {}

    for installment in purchase_installments:
        installments_by_purchase.setdefault(
            installment.purchase_id,
            []
        ).append({
            "id": installment.id,
            "installment_number": installment.installment_number,
            "total_installments": installment.total_installments,
            "due_date": installment.due_date,
            "amount": float(installment.amount or 0),
            "posted": bool(installment.posted),
            "posted_date": installment.posted_date
        })

    for schedule in installments_by_purchase.values():
        schedule.sort(
            key=lambda item: (
                item["installment_number"],
                item["id"]
            )
        )

    result = []

    for purchase in purchases:

        supplier_value = str(
            purchase.supplier or ""
        ).strip()

        supplier_name = supplier_name_by_id.get(
            supplier_value
        )

        if not supplier_name:

            supplier_name = supplier_name_by_name.get(
                supplier_value.lower()
            )

        if not supplier_name:

            supplier_name = supplier_value or "Sin proveedor"

        raw_notes = str(purchase.notes or "")
        metadata = {}
        visible_notes = raw_notes

        if raw_notes.startswith(PURCHASE_METADATA_PREFIX):

            try:

                metadata = json.loads(
                    raw_notes[len(PURCHASE_METADATA_PREFIX):]
                )
                visible_notes = str(
                    metadata.get("notes", "")
                )

            except Exception:

                metadata = {}
                visible_notes = raw_notes

        extra_items = metadata.get("extra_items", [])

        if not isinstance(extra_items, list):

            extra_items = []

        result.append({
            "id": purchase.id,
            "number": purchase.number,
            "supplier": supplier_name,
            "supplier_reference": supplier_value,
            "invoice_number": purchase.invoice_number,
            "payment_method": purchase.payment_method,
            "date": purchase.date,
            "notes": visible_notes,
            "shipping_cost": float(
                metadata.get("shipping_cost", 0) or 0
            ),
            "extra_items": extra_items,
            "total": float(purchase.total or 0),
            "items": items_by_purchase.get(purchase.id, []),
            "installments": installments_by_purchase.get(
                purchase.id,
                []
            ),
            "installments_count": (
                installments_by_purchase.get(
                    purchase.id,
                    [{}]
                )[0].get("total_installments", 0)
                if installments_by_purchase.get(purchase.id)
                else 0
            )
        })

    return result


@app.post("/purchases")
def create_purchase(
    data: dict,
    db: Session = Depends(get_db)
):

    purchase_number = (
        take_next_document_number(
            db,
            "PURCHASE"
        )
    )

    purchase = Purchase(

        number=purchase_number,

        supplier=data["supplier"],

        invoice_number=data.get("invoice_number", ""),

        payment_method=data.get("payment_method", "Caja"),

        date=data["date"],

        notes=data.get("notes", ""),

        total=0

    )

    db.add(purchase)

    db.commit()

    db.refresh(purchase)

    return purchase

PURCHASE_METADATA_PREFIX = (
    "__NATIVA_PURCHASE_META__"
)


def purchase_payment_account(
    payment_method
):

    if payment_method == "Banco":

        return (
            "1.1.02",
            "Banco"
        )

    if payment_method == "Mercado Pago":

        return (
            "1.1.06",
            "Mercado Pago"
        )

    if payment_method in [
        "Tarjeta",
        "Tarjeta de crédito"
    ]:

        return (
            "2.1.03",
            "Tarjeta de crédito a pagar"
        )

    if payment_method in [
        "Proveedores",
        "Cuenta corriente"
    ]:

        return (
            "2.1.01",
            "Proveedores"
        )

    return (
        "1.1.01",
        "Caja"
    )


def purchase_installments_count(purchase, data):
    if normalize_account_label(purchase.payment_method) not in {
        "tarjeta",
        "tarjeta de credito"
    }:
        return 0

    raw_value = data.get("installments_count", 0)
    if raw_value in {None, ""}:
        return 0

    try:
        count = int(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError("La cantidad de cuotas no es válida") from error

    if count < 0 or count > 60:
        raise ValueError("La cantidad de cuotas debe estar entre 0 y 60")

    return count


def remove_purchase_installments(db, purchase):
    installments = db.query(PurchaseInstallment).filter(
        PurchaseInstallment.purchase_id == purchase.id
    ).all()
    installment_ids = [
        item.id for item in installments if item.id is not None
    ]

    if installment_ids:
        db.query(JournalEntry).filter(
            JournalEntry.origin == "VENCIMIENTO_TARJETA",
            JournalEntry.origin_id.in_(installment_ids)
        ).delete(synchronize_session=False)

    db.query(JournalEntry).filter(
        JournalEntry.origin == "CUOTAS_TARJETA",
        JournalEntry.origin_id == purchase.id
    ).delete(synchronize_session=False)

    for installment in installments:
        db.delete(installment)


def create_purchase_installments(db, purchase, total, count):
    if count <= 0:
        return

    purchase_date = parse_date_value(purchase.date, "fecha de compra")
    total = round(float(total or 0), 2)
    base_amount = round(total / count, 2)
    remaining = total

    for number in range(1, count + 1):
        amount = base_amount if number < count else round(remaining, 2)
        remaining = round(remaining - amount, 2)

        db.add(PurchaseInstallment(
            purchase_id=purchase.id,
            installment_number=number,
            total_installments=count,
            due_date=str(purchase_date + timedelta(days=30 * number)),
            amount=amount,
            posted=0
        ))

    db.flush()

    registrar_asiento(
        db=db,
        fecha=purchase.date,
        concepto=f"Cuotas tarjeta compra {purchase.number}",
        debe_codigo="2.1.03",
        debe_nombre="Tarjeta de crédito a pagar",
        haber_codigo="2.1.04",
        haber_nombre="Cuotas de tarjeta a vencer",
        importe=total,
        origin="CUOTAS_TARJETA",
        origin_id=purchase.id
    )


def post_due_credit_card_installments(db):
    today = datetime.now(
        timezone(timedelta(hours=-3))
    ).date()
    today_text = str(today)

    pending = db.query(PurchaseInstallment).filter(
        PurchaseInstallment.posted == 0,
        PurchaseInstallment.due_date <= today_text
    ).order_by(
        PurchaseInstallment.due_date.asc(),
        PurchaseInstallment.id.asc()
    ).all()

    for installment in pending:
        purchase = db.query(Purchase).filter(
            Purchase.id == installment.purchase_id
        ).first()
        if not purchase:
            continue

        existing = db.query(JournalEntry).filter(
            JournalEntry.origin == "VENCIMIENTO_TARJETA",
            JournalEntry.origin_id == installment.id
        ).first()

        if existing:
            installment.posted = 1
            installment.posted_date = installment.posted_date or today_text
            installment.journal_group = (
                installment.journal_group or existing.entry_group
            )
            continue

        group_id = registrar_asiento(
            db=db,
            fecha=installment.due_date,
            concepto=(
                f"Cuota {installment.installment_number}/"
                f"{installment.total_installments} tarjeta "
                f"- Compra {purchase.number}"
            ),
            debe_codigo="2.1.04",
            debe_nombre="Cuotas de tarjeta a vencer",
            haber_codigo="2.1.03",
            haber_nombre="Tarjeta de crédito a pagar",
            importe=round(float(installment.amount or 0), 2),
            origin="VENCIMIENTO_TARJETA",
            origin_id=installment.id
        )

        installment.posted = 1
        installment.posted_date = today_text
        installment.journal_group = group_id

    if pending:
        db.flush()


def clean_purchase_payload(
    data
):

    items = data.get("items", [])
    extra_items = data.get("extra_items", [])
    shipping_cost = max(
        float(data.get("shipping_cost", 0) or 0),
        0
    )

    clean_items = []

    for item in items:

        item_type = str(
            item.get("item_type", "")
            or
            ""
        ).strip().upper()

        product_id_value = item.get("product_id")
        raw_material_id_value = item.get("raw_material_id")

        if (
            item_type in {"RESALE", "REVENTA"}
            or
            product_id_value not in {None, ""}
        ):

            item_type = "RESALE"
            inventory_id = int(product_id_value)

        else:

            item_type = "RAW_MATERIAL"
            inventory_id = int(raw_material_id_value)

        quantity = float(item.get("quantity", 0) or 0)
        price = float(item.get("price", 0) or 0)

        if quantity <= 0:

            raise ValueError(
                "Las cantidades deben ser mayores a cero"
            )

        if price < 0:

            raise ValueError(
                "Los precios no pueden ser negativos"
            )

        clean_items.append({
            "item_type": item_type,
            "inventory_id": inventory_id,
            "raw_material_id": (
                inventory_id
                if item_type == "RAW_MATERIAL"
                else None
            ),
            "product_id": (
                inventory_id
                if item_type == "RESALE"
                else None
            ),
            "quantity": quantity,
            "price": price
        })

    clean_extra_items = []

    for item in extra_items:

        name = str(item.get("name", "") or "").strip()
        category = str(
            item.get("category", "Herramientas y utensilios")
            or
            "Herramientas y utensilios"
        ).strip()
        quantity = float(item.get("quantity", 0) or 0)
        price = float(item.get("price", 0) or 0)

        if not name:

            continue

        if quantity <= 0:

            raise ValueError(
                "Las cantidades de los materiales de producción deben ser mayores a cero"
            )

        if price < 0:

            raise ValueError(
                "Los importes de los materiales de producción no pueden ser negativos"
            )

        clean_extra_items.append({
            "item_type": "PRODUCTION_MATERIAL",
            "name": name,
            "category": category,
            "quantity": quantity,
            "price": price
        })

    if not clean_items and not clean_extra_items and shipping_cost <= 0:

        raise ValueError(
            "La compra no tiene importes válidos"
        )

    return (clean_items, clean_extra_items, shipping_cost)


def purchase_quantities_by_inventory(
    db,
    purchase_id
):

    result = {}

    for item in db.query(PurchaseItem).filter(
        PurchaseItem.purchase_id == purchase_id
    ).all():

        if item.product_id:

            key = ("RESALE", int(item.product_id))

        else:

            key = (
                "RAW_MATERIAL",
                int(item.raw_material_id)
            )

        result[key] = (
            result.get(key, 0)
            +
            float(item.quantity or 0)
        )

    return result


def remove_purchase_contents(
    db,
    purchase,
    adjust_stock=True
):

    purchase_items = db.query(PurchaseItem).filter(
        PurchaseItem.purchase_id == purchase.id
    ).all()

    quantities = purchase_quantities_by_inventory(
        db,
        purchase.id
    )

    inventory_by_key = {}

    if adjust_stock:

        for key, quantity in quantities.items():

            item_type, inventory_id = key

            if item_type == "RESALE":

                inventory = (
                    db.query(Product)
                    .filter(Product.id == inventory_id)
                    .with_for_update()
                    .first()
                )

                if inventory and not is_resale_product(inventory):

                    raise ValueError(
                        f"{inventory.name} ya no está marcado como producto de reventa"
                    )

            else:

                inventory = (
                    db.query(RawMaterial)
                    .filter(RawMaterial.id == inventory_id)
                    .with_for_update()
                    .first()
                )

            if not inventory:

                continue

            if float(inventory.stock or 0) + 0.000001 < quantity:

                raise ValueError(
                    (
                        "No se puede revertir la compra porque "
                        f"ya se consumió parte del stock de {inventory.name}. "
                        f"Stock actual: {float(inventory.stock or 0)}"
                    )
                )

            inventory_by_key[key] = inventory

        for key, quantity in quantities.items():

            inventory = inventory_by_key.get(key)

            if inventory:

                inventory.stock = (
                    float(inventory.stock or 0)
                    -
                    quantity
                )

    remove_purchase_installments(
        db,
        purchase
    )

    for item in purchase_items:

        db.delete(item)

    db.query(JournalEntry).filter(
        JournalEntry.origin == "COMPRA",
        JournalEntry.origin_id == purchase.id
    ).delete(synchronize_session=False)

    db.query(JournalEntry).filter(
        JournalEntry.origin_id.is_(None),
        JournalEntry.concept == f"Compra {purchase.number}"
    ).delete(synchronize_session=False)

    purchase.total = 0
    db.flush()

    material_ids = {
        inventory_id
        for item_type, inventory_id in quantities
        if item_type == "RAW_MATERIAL"
    }
    product_ids = {
        inventory_id
        for item_type, inventory_id in quantities
        if item_type == "RESALE"
    }

    return material_ids, product_ids


def recalculate_raw_material_costs(
    db,
    material_ids
):

    for material_id in set(material_ids):

        material = db.query(RawMaterial).filter(
            RawMaterial.id == material_id
        ).first()

        if not material:

            continue

        latest_item = (
            db.query(PurchaseItem)
            .join(
                Purchase,
                PurchaseItem.purchase_id == Purchase.id
            )
            .filter(
                PurchaseItem.raw_material_id == material_id,
                PurchaseItem.product_id.is_(None)
            )
            .order_by(
                Purchase.date.desc(),
                PurchaseItem.id.desc()
            )
            .first()
        )

        if latest_item and float(latest_item.quantity or 0) > 0:

            material.cost = (
                float(latest_item.price or 0)
                /
                float(latest_item.quantity or 0)
            )

        else:

            material.cost = 0


def recalculate_resale_product_costs(
    db,
    product_ids
):

    for product_id in set(product_ids):

        product = db.query(Product).filter(
            Product.id == product_id
        ).first()

        if not product:

            continue

        latest_item = (
            db.query(PurchaseItem)
            .join(
                Purchase,
                PurchaseItem.purchase_id == Purchase.id
            )
            .filter(
                PurchaseItem.product_id == product_id
            )
            .order_by(
                Purchase.date.desc(),
                PurchaseItem.id.desc()
            )
            .first()
        )

        if latest_item and float(latest_item.quantity or 0) > 0:

            product.unit_cost = (
                float(latest_item.price or 0)
                /
                float(latest_item.quantity or 0)
            )

        elif float(product.stock or 0) <= 0.000001:

            product.unit_cost = 0


def apply_purchase_contents(
    db,
    purchase,
    data,
    adjust_stock=True,
    cleaned_payload=None
):

    if cleaned_payload is None:

        (
            clean_items,
            clean_extra_items,
            shipping_cost
        ) = clean_purchase_payload(data)

    else:

        (
            clean_items,
            clean_extra_items,
            shipping_cost
        ) = cleaned_payload

    inventory_by_key = {}

    for item in clean_items:

        key = (item["item_type"], item["inventory_id"])

        if item["item_type"] == "RESALE":

            inventory = (
                db.query(Product)
                .filter(Product.id == item["inventory_id"])
                .with_for_update()
                .first()
            )

            if not inventory or not is_resale_product(inventory):

                raise ValueError(
                    "Uno de los productos de reventa no existe o no está marcado como reventa"
                )

        else:

            inventory = (
                db.query(RawMaterial)
                .filter(RawMaterial.id == item["inventory_id"])
                .with_for_update()
                .first()
            )

            if not inventory:

                raise ValueError(
                    "Una de las materias primas no existe"
                )

        inventory_by_key[key] = inventory

    inventory_base_total = sum(
        item["price"]
        for item in clean_items
    )
    extra_base_total = sum(
        item["price"]
        for item in clean_extra_items
    )
    allocation_base_total = (
        inventory_base_total
        +
        extra_base_total
    )

    material_total = 0
    resale_total = 0
    affected_material_ids = set()
    affected_product_ids = set()

    for item in clean_items:

        key = (item["item_type"], item["inventory_id"])
        inventory = inventory_by_key[key]

        allocated_shipping = 0

        if allocation_base_total > 0:

            allocated_shipping = (
                shipping_cost
                *
                item["price"]
                /
                allocation_base_total
            )

        final_price = item["price"] + allocated_shipping

        db.add(
            PurchaseItem(
                purchase_id=purchase.id,
                raw_material_id=item["raw_material_id"],
                product_id=item["product_id"],
                quantity=item["quantity"],
                price=final_price
            )
        )

        if adjust_stock:

            purchased_quantity = float(item["quantity"] or 0)

            if purchased_quantity <= 0:

                raise ValueError(
                    f"La cantidad comprada de {inventory.name} debe ser mayor a cero"
                )

            previous_stock = max(
                float(inventory.stock or 0),
                0
            )

            previous_unit_cost = max(
                float(
                    inventory.unit_cost
                    if item["item_type"] == "RESALE"
                    else inventory.cost
                )
                or
                0,
                0
            )

            previous_stock_value = (
                previous_stock
                *
                previous_unit_cost
            )
            new_stock = previous_stock + purchased_quantity
            new_unit_cost = (
                previous_stock_value + final_price
            ) / new_stock

            if item["item_type"] == "RESALE":

                inventory.unit_cost = new_unit_cost

            else:

                inventory.cost = new_unit_cost

            inventory.stock = new_stock

        if item["item_type"] == "RESALE":

            resale_total += final_price
            affected_product_ids.add(inventory.id)

        else:

            material_total += final_price
            affected_material_ids.add(inventory.id)

    extra_total = 0
    extra_items_with_shipping = []

    for item in clean_extra_items:

        allocated_shipping = 0

        if allocation_base_total > 0:

            allocated_shipping = (
                shipping_cost
                *
                item["price"]
                /
                allocation_base_total
            )

        final_price = (
            item["price"]
            +
            allocated_shipping
        )

        extra_total += final_price

        extra_items_with_shipping.append({
            **item,
            "base_price": item["price"],
            "shipping_allocated": allocated_shipping,
            "final_price": final_price
        })

    unallocated_shipping = (
        shipping_cost
        if allocation_base_total <= 0
        else 0
    )
    expense_total = extra_total + unallocated_shipping
    total = material_total + resale_total + expense_total

    if total <= 0:

        raise ValueError(
            "La compra no tiene importes válidos"
        )

    metadata = {
        "shipping_cost": shipping_cost,
        "extra_items": extra_items_with_shipping,
        "notes": str(data.get("notes", "") or "")
    }

    purchase.notes = (
        PURCHASE_METADATA_PREFIX
        +
        json.dumps(metadata, ensure_ascii=False)
    )
    purchase.total = total

    payment_code, payment_name = purchase_payment_account(
        purchase.payment_method
    )
    group_id = str(uuid4())

    if material_total > 0:

        db.add(
            JournalEntry(
                date=purchase.date,
                concept=f"Compra {purchase.number}",
                account_code="1.2.01",
                account_name="Materia Prima",
                debit=material_total,
                credit=0,
                entry_group=group_id,
                origin="COMPRA",
                origin_id=purchase.id
            )
        )

    if resale_total > 0:

        db.add(
            JournalEntry(
                date=purchase.date,
                concept=f"Compra {purchase.number}",
                account_code="1.2.03",
                account_name="Mercadería para reventa",
                debit=resale_total,
                credit=0,
                entry_group=group_id,
                origin="COMPRA",
                origin_id=purchase.id
            )
        )

    if expense_total > 0:

        db.add(
            JournalEntry(
                date=purchase.date,
                concept=f"Compra {purchase.number}",
                account_code="5.1.12",
                account_name="Materiales y gastos de producción",
                debit=expense_total,
                credit=0,
                entry_group=group_id,
                origin="COMPRA",
                origin_id=purchase.id
            )
        )

    db.add(
        JournalEntry(
            date=purchase.date,
            concept=f"Compra {purchase.number}",
            account_code=payment_code,
            account_name=payment_name,
            debit=0,
            credit=total,
            entry_group=group_id,
            origin="COMPRA",
            origin_id=purchase.id
        )
    )

    db.flush()

    installments_count = purchase_installments_count(
        purchase,
        data
    )

    if installments_count > 0:
        create_purchase_installments(
            db,
            purchase,
            total,
            installments_count
        )

    if not adjust_stock:

        recalculate_raw_material_costs(
            db,
            affected_material_ids
        )
        recalculate_resale_product_costs(
            db,
            affected_product_ids
        )

    return (
        total,
        affected_material_ids,
        affected_product_ids
    )


@app.post("/purchase-items")
def create_purchase_items(
    data: dict,
    db: Session = Depends(get_db)
):

    purchase = db.query(Purchase).filter(
        Purchase.id == data.get("purchase_id")
    ).first()

    if not purchase:

        return {
            "error":
            "Compra no encontrada"
        }

    try:

        total, _, _ = apply_purchase_contents(
            db,
            purchase,
            data
        )

        db.commit()

        return {
            "message":
            "Compra completa guardada y contabilizada",
            "total":
            total
        }

    except Exception as error:

        db.rollback()

        empty_purchase = db.query(Purchase).filter(
            Purchase.id == data.get("purchase_id")
        ).first()

        if empty_purchase:

            existing_item = db.query(PurchaseItem).filter(
                PurchaseItem.purchase_id == empty_purchase.id
            ).first()

            if not existing_item:

                db.delete(empty_purchase)
                db.commit()

        return {
            "error":
            f"No se pudo guardar la compra: {error}"
        }


@app.put("/purchases/{purchase_id}")
def update_purchase(
    purchase_id: int,
    data: dict,
    db: Session = Depends(get_db)
):

    purchase = db.query(Purchase).filter(
        Purchase.id == purchase_id
    ).first()

    if not purchase:

        return {"error": "Compra no encontrada"}

    posted_installment = db.query(PurchaseInstallment).filter(
        PurchaseInstallment.purchase_id == purchase.id,
        PurchaseInstallment.posted == 1
    ).first()

    if posted_installment:
        return {
            "error":
            (
                "No se puede modificar esta compra porque ya tiene "
                "cuotas contabilizadas como exigibles. "
                "El historial contable se conserva sin cambios."
            )
        }

    try:

        cleaned_payload = clean_purchase_payload(data)
        clean_items = cleaned_payload[0]

        old_quantities = purchase_quantities_by_inventory(
            db,
            purchase.id
        )
        new_quantities = {}

        for item in clean_items:

            key = (item["item_type"], item["inventory_id"])
            new_quantities[key] = (
                new_quantities.get(key, 0)
                +
                item["quantity"]
            )

        all_keys = set(old_quantities) | set(new_quantities)
        inventories_by_key = {}

        for key in all_keys:

            item_type, inventory_id = key

            if item_type == "RESALE":

                inventory = (
                    db.query(Product)
                    .filter(Product.id == inventory_id)
                    .with_for_update()
                    .first()
                )

                if inventory and not is_resale_product(inventory):

                    raise ValueError(
                        f"{inventory.name} ya no está marcado como producto de reventa"
                    )

            else:

                inventory = (
                    db.query(RawMaterial)
                    .filter(RawMaterial.id == inventory_id)
                    .with_for_update()
                    .first()
                )

            if not inventory:

                raise ValueError(
                    "Uno de los artículos de la compra no existe"
                )

            delta = (
                new_quantities.get(key, 0)
                -
                old_quantities.get(key, 0)
            )

            if float(inventory.stock or 0) + delta < -0.000001:

                raise ValueError(
                    (
                        f"No se puede reducir esa cantidad de {inventory.name} "
                        "porque parte del stock ya fue consumido. "
                        f"Stock actual: {float(inventory.stock or 0)}"
                    )
                )

            inventories_by_key[key] = (inventory, delta)

        old_material_ids, old_product_ids = remove_purchase_contents(
            db,
            purchase,
            adjust_stock=False
        )

        for inventory, delta in inventories_by_key.values():

            inventory.stock = float(inventory.stock or 0) + delta

        purchase.supplier = str(
            data.get("supplier", purchase.supplier)
        ).strip()
        purchase.invoice_number = str(
            data.get("invoice_number", "") or ""
        ).strip()
        purchase.payment_method = str(
            data.get("payment_method", "Caja") or "Caja"
        ).strip()
        purchase.date = str(
            data.get("date", purchase.date)
        ).strip()

        (
            total,
            new_material_ids,
            new_product_ids
        ) = apply_purchase_contents(
            db,
            purchase,
            data,
            adjust_stock=False,
            cleaned_payload=cleaned_payload
        )

        recalculate_raw_material_costs(
            db,
            old_material_ids | new_material_ids
        )
        recalculate_resale_product_costs(
            db,
            old_product_ids | new_product_ids
        )

        db.commit()

        return {
            "message":
            f"Compra {purchase.number} modificada correctamente",
            "total": total
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo modificar la compra: {error}"
        }


# ================= COMPRAS ITEMS =================

# ================= COMPRAS ITEMS =================

@app.post("/purchase-item/{purchase_id}/{product_id}/{qty}")
def add_purchase_item(
    purchase_id: int,
    product_id: int,
    qty: float,
    db: Session = Depends(get_db)
):

    product = db.query(Product).filter(
        Product.id == product_id
    ).first()
    purchase = db.query(Purchase).filter(
        Purchase.id == purchase_id
    ).first()

    if not product or not purchase:

        return {
            "error":
            "Compra o producto no encontrado"
        }

    if not is_resale_product(product):

        return {
            "error":
            "Este endpoint solo admite productos de reventa"
        }

    quantity = float(qty or 0)

    if quantity <= 0:

        return {
            "error":
            "La cantidad debe ser mayor a cero"
        }

    unit_cost = max(float(product.unit_cost or 0), 0)
    subtotal = unit_cost * quantity

    item = PurchaseItem(
        purchase_id=purchase.id,
        raw_material_id=None,
        product_id=product.id,
        quantity=quantity,
        price=subtotal
    )

    product.stock = float(product.stock or 0) + quantity
    purchase.total = float(purchase.total or 0) + subtotal
    db.add(item)
    db.commit()

    return {"mensaje": "compra actualizada"}

@app.delete("/purchases/{purchase_id}")
def delete_purchase(
    purchase_id: int,
    db: Session = Depends(get_db)
):

    purchase = db.query(Purchase).filter(
        Purchase.id == purchase_id
    ).first()

    if not purchase:

        return {
            "error":
            "Compra no encontrada"
        }

    posted_installment = db.query(PurchaseInstallment).filter(
        PurchaseInstallment.purchase_id == purchase.id,
        PurchaseInstallment.posted == 1
    ).first()

    if posted_installment:
        return {
            "error":
            (
                "No se puede eliminar esta compra porque ya tiene "
                "cuotas contabilizadas como exigibles. "
                "El historial contable se conserva sin cambios."
            )
        }

    try:

        (
            affected_material_ids,
            affected_product_ids
        ) = remove_purchase_contents(
            db,
            purchase
        )

        purchase_number = purchase.number

        db.delete(purchase)
        db.flush()

        recalculate_raw_material_costs(
            db,
            affected_material_ids
        )
        recalculate_resale_product_costs(
            db,
            affected_product_ids
        )

        db.commit()

        return {
            "message":
            f"Compra {purchase_number} eliminada correctamente"
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo eliminar la compra: {error}"
        }


# ================= CONTABILIDAD =================

@app.get("/accounting")
def get_accounting(
    db: Session = Depends(get_db)
):

    return db.query(Accounting).all()

@app.get("/accounts")
def get_accounts(
    db: Session = Depends(get_db)
):

    return (
        db.query(Account)
        .order_by(Account.code.asc())
        .all()
    )
    
@app.post("/accounts")
def create_account(
    data: dict,
    db: Session = Depends(get_db)
):

    code = str(data.get("code", "")).strip()
    name = str(data.get("name", "")).strip()

    if not code or not name:
        return {"error": "El código y el nombre son obligatorios"}

    if db.query(Account).filter(Account.code == code).first():
        return {"error": f"Ya existe una cuenta con el código {code}"}

    normalized_name = normalize_account_label(name)
    for existing in db.query(Account).all():
        if normalize_account_label(existing.name) == normalized_name:
            return {
                "error":
                f"Ya existe la cuenta {existing.code} - {existing.name}"
            }

    account = Account(

        code=code,

        name=name,

        type=data["type"],

        category=data.get(
            "category",
            ""
        ),

        active=1
    )


    db.add(account)

    db.commit()

    db.refresh(account)


    return account

@app.delete("/accounts/{account_id}")
def delete_account(
    account_id:int,
    db:Session=Depends(get_db)
):

    account = db.query(Account).filter(
        Account.id == account_id
    ).first()


    if not account:

        return {
            "error":"Cuenta inexistente"
        }


    db.delete(account)

    db.commit()


    return {
        "mensaje":"Cuenta eliminada"
    }        

def registrar_asiento(

    db,

    fecha,

    concepto,

    debe_codigo,

    debe_nombre,

    haber_codigo,

    haber_nombre,

    importe,

    origin="MANUAL",

    origin_id=None,

    entry_group=None

):

    group_id = (
        entry_group
        or
        str(uuid4())
    )

    debe = JournalEntry(

        date=fecha,

        concept=concepto,

        account_code=debe_codigo,

        account_name=debe_nombre,

        debit=importe,

        credit=0,

        entry_group=group_id,

        origin=origin,

        origin_id=origin_id

    )


    haber = JournalEntry(

        date=fecha,

        concept=concepto,

        account_code=haber_codigo,

        account_name=haber_nombre,

        debit=0,

        credit=importe,

        entry_group=group_id,

        origin=origin,

        origin_id=origin_id

    )


    db.add(debe)

    db.add(haber)

    db.flush()

    return group_id


def registrar_asiento_produccion(

    db,

    fecha,

    concepto,

    costo_materiales,

    costo_mano_obra,

    origin_id=None

):

    group_id = str(
        uuid4()
    )

    lineas = []

    if costo_materiales > 0:

        lineas.append(
            JournalEntry(
                date=fecha,
                concept=concepto,
                account_code="1.2.02",
                account_name="Productos Terminados",
                debit=costo_materiales,
                credit=0,
                entry_group=group_id,
                origin="PRODUCCION",
                origin_id=origin_id
            )
        )

        lineas.append(
            JournalEntry(
                date=fecha,
                concept=concepto,
                account_code="1.2.01",
                account_name="Materia Prima",
                debit=0,
                credit=costo_materiales,
                entry_group=group_id,
                origin="PRODUCCION",
                origin_id=origin_id
            )
        )

    if costo_mano_obra > 0:

        lineas.append(
            JournalEntry(
                date=fecha,
                concept=concepto,
                account_code="5.1.02",
                account_name="Mano de obra",
                debit=costo_mano_obra,
                credit=0,
                entry_group=group_id,
                origin="PRODUCCION",
                origin_id=origin_id
            )
        )

        lineas.append(
            JournalEntry(
                date=fecha,
                concept=concepto,
                account_code="2.1.02",
                account_name="Sueldos a Pagar",
                debit=0,
                credit=costo_mano_obra,
                entry_group=group_id,
                origin="PRODUCCION",
                origin_id=origin_id
            )
        )

    for linea in lineas:

        db.add(linea)

    db.flush()

    return group_id


def validate_journal_lines(
    db,
    lines
):

    if not isinstance(
        lines,
        list
    ) or len(lines) < 2:

        return (
            None,
            "El asiento debe tener al menos dos renglones"
        )

    validated = []

    total_debit = 0

    total_credit = 0

    for index, line in enumerate(
        lines,
        start=1
    ):

        account_code = str(
            line.get(
                "account_code",
                ""
            )
        ).strip()

        if not account_code:

            return (
                None,
                f"Falta la cuenta del renglón {index}"
            )

        account = db.query(Account).filter(
            Account.code
            ==
            account_code
        ).first()

        if not account:

            return (
                None,
                f"La cuenta {account_code} no existe"
            )

        try:

            debit = round(
                float(
                    line.get(
                        "debit",
                        0
                    )
                    or
                    0
                ),
                2
            )

            credit = round(
                float(
                    line.get(
                        "credit",
                        0
                    )
                    or
                    0
                ),
                2
            )

        except (
            TypeError,
            ValueError
        ):

            return (
                None,
                f"Importe inválido en el renglón {index}"
            )

        if debit < 0 or credit < 0:

            return (
                None,
                "Los importes no pueden ser negativos"
            )

        if debit > 0 and credit > 0:

            return (
                None,
                (
                    f"El renglón {index} no puede tener "
                    "importe en Debe y Haber al mismo tiempo"
                )
            )

        if debit <= 0 and credit <= 0:

            return (
                None,
                f"El renglón {index} no tiene importe"
            )

        total_debit += debit

        total_credit += credit

        validated.append({

            "account_code":
            account.code,

            "account_name":
            account.name,

            "debit":
            debit,

            "credit":
            credit

        })

    total_debit = round(
        total_debit,
        2
    )

    total_credit = round(
        total_credit,
        2
    )

    if total_debit <= 0:

        return (
            None,
            "El total del asiento debe ser mayor a cero"
        )

    if abs(
        total_debit
        -
        total_credit
    ) > 0.009:

        return (
            None,
            (
                "El asiento está desbalanceado. "
                f"Debe: {total_debit:.2f} - "
                f"Haber: {total_credit:.2f}"
            )
        )

    return (
        validated,
        None
    )


@app.post("/journal-entry")
def create_journal_entry(
    data: dict,
    db: Session = Depends(get_db)
):

    date = str(
        data.get(
            "date",
            ""
        )
    ).strip()

    concept = str(
        data.get(
            "concept",
            ""
        )
    ).strip()

    if not date:

        return {
            "error":
            "La fecha es obligatoria"
        }

    if not concept:

        return {
            "error":
            "El concepto es obligatorio"
        }

    lines = data.get(
        "lines"
    )

    # Compatibilidad con el formulario simple anterior.
    if not lines:

        lines = [

            {
                "account_code":
                data.get("debit_code"),

                "debit":
                data.get("amount", 0),

                "credit":
                0
            },

            {
                "account_code":
                data.get("credit_code"),

                "debit":
                0,

                "credit":
                data.get("amount", 0)
            }

        ]

    validated_lines, error = (
        validate_journal_lines(
            db,
            lines
        )
    )

    if error:

        return {
            "error":
            error
        }

    group_id = str(
        uuid4()
    )

    for line in validated_lines:

        db.add(
            JournalEntry(

                date=date,

                concept=concept,

                account_code=
                line["account_code"],

                account_name=
                line["account_name"],

                debit=
                line["debit"],

                credit=
                line["credit"],

                entry_group=
                group_id,

                origin=
                "MANUAL",

                origin_id=
                None

            )
        )

    db.commit()

    return {

        "mensaje":
        "Asiento registrado",

        "entry_group":
        group_id

    }


@app.get("/journal-entry")
def get_journal_entries(
    db: Session = Depends(get_db)
):

    post_due_credit_card_installments(db)

    ensure_journal_entry_numbers(db)

    return (
        db.query(JournalEntry)
        .order_by(
            JournalEntry.date.asc(),
            JournalEntry.id.asc()
        )
        .all()
    )


@app.put("/journal-entry-group/{group_id}")
def update_journal_entry_group(
    group_id: str,
    data: dict,
    db: Session = Depends(get_db)
):

    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.entry_group
            ==
            group_id
        )
        .order_by(
            JournalEntry.id.asc()
        )
        .all()
    )

    if not entries:

        return {
            "error":
            "Asiento no encontrado"
        }

    date = str(
        data.get(
            "date",
            ""
        )
    ).strip()

    concept = str(
        data.get(
            "concept",
            ""
        )
    ).strip()

    if not date:

        return {
            "error":
            "La fecha es obligatoria"
        }

    if not concept:

        return {
            "error":
            "El concepto es obligatorio"
        }

    validated_lines, error = (
        validate_journal_lines(
            db,
            data.get(
                "lines",
                []
            )
        )
    )

    if error:

        return {
            "error":
            error
        }

    origin = (
        entries[0].origin
        or
        infer_journal_origin(
            entries[0].concept
        )
    )

    origin_id = (
        entries[0].origin_id
    )

    entry_number = entries[0].entry_number

    try:

        for entry in entries:

            db.delete(entry)

        db.flush()

        for line in validated_lines:

            db.add(
                JournalEntry(

                    date=date,

                    concept=concept,

                    account_code=
                    line["account_code"],

                    account_name=
                    line["account_name"],

                    debit=
                    line["debit"],

                    credit=
                    line["credit"],

                    entry_group=
                    group_id,

                    origin=
                    origin,

                    origin_id=
                    origin_id,

                    entry_number=
                    entry_number

                )
            )

        db.commit()

        return {

            "mensaje":
            "Asiento actualizado correctamente",

            "entry_group":
            group_id

        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo actualizar el asiento: {error}"
        }


@app.delete("/journal-entry-group/{group_id}")
def delete_journal_entry_group(
    group_id: str,
    db: Session = Depends(get_db)
):

    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.entry_group
            ==
            group_id
        )
        .all()
    )

    if not entries:

        return {
            "error":
            "Asiento no encontrado"
        }

    origin = (
        entries[0].origin
        or
        infer_journal_origin(
            entries[0].concept
        )
    )

    try:

        for entry in entries:

            db.delete(entry)

        db.commit()

        return {

            "mensaje":
            "Asiento eliminado correctamente",

            "origin":
            origin,

            "advertencia":
            (
                "Se eliminó únicamente el registro contable. "
                "La operación de origen y el stock no fueron modificados."
                if origin != "MANUAL"
                else
                ""
            )

        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo eliminar el asiento: {error}"
        }


@app.get("/debug-journal")
def debug_journal(
    db: Session = Depends(get_db)
):

    resultado = db.execute(
        text("SELECT * FROM journal_entries")
    ).mappings().all()

    return resultado


# ================= DASHBOARD =================

@app.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db)
):

    now = datetime.now()

    current_month = now.strftime(
        "%Y-%m"
    )

    period = now.strftime(
        "%m/%Y"
    )


    def numeric(
        value
    ):

        try:

            return float(
                value or 0
            )

        except (
            TypeError,
            ValueError
        ):

            return 0


    def normalized_date(
        value
    ):

        if value is None:

            return ""

        return str(value)[:10]


    def belongs_to_current_month(
        value
    ):

        return (
            normalized_date(value)[:7]
            ==
            current_month
        )


    sales = db.query(Sale).all()

    purchases = db.query(Purchase).all()

    lots = db.query(Lot).all()

    products = db.query(Product).all()

    raw_materials = (
        db.query(RawMaterial).all()
    )

    formulas = db.query(Formula).all()

    suppliers = db.query(Supplier).all()

    accounts = db.query(Account).all()

    journal_entries = (
        db.query(JournalEntry).all()
    )


    sales_month_list = [

        sale

        for sale in sales

        if belongs_to_current_month(
            sale.date
        )

    ]


    purchases_month_list = [

        purchase

        for purchase in purchases

        if belongs_to_current_month(
            purchase.date
        )

    ]


    lots_month_list = [

        lot

        for lot in lots

        if belongs_to_current_month(
            lot.production_date
        )

    ]


    account_type_by_code = {

        account.code:
        str(account.type or "").upper()

        for account in accounts

    }


    journal_month = [

        entry

        for entry in journal_entries

        if belongs_to_current_month(
            entry.date
        )

    ]


    income_month = sum(

        numeric(entry.credit)
        -
        numeric(entry.debit)

        for entry in journal_month

        if account_type_by_code.get(
            entry.account_code
        )
        ==
        "INGRESO"

    )


    costs_month = sum(

        numeric(entry.debit)
        -
        numeric(entry.credit)

        for entry in journal_month

        if account_type_by_code.get(
            entry.account_code
        )
        ==
        "COSTO"

    )


    expenses_month = sum(

        numeric(entry.debit)
        -
        numeric(entry.credit)

        for entry in journal_month

        if account_type_by_code.get(
            entry.account_code
        )
        ==
        "GASTO"

    )


    raw_material_alerts = [

        {

            "id":
            material.id,

            "name":
            material.name,

            "stock":
            numeric(
                material.stock
            ),

            "minimum_stock":
            numeric(
                material.minimum_stock
            ),

            "unit":
            material.unit

        }

        for material in raw_materials

        if numeric(
            material.stock
        )
        <=
        numeric(
            material.minimum_stock
        )

    ]


    product_alerts = [

        {

            "id":
            product.id,

            "name":
            product.name,

            "stock":
            numeric(
                product.stock
            )

        }

        for product in products

        if numeric(
            product.stock
        )
        <=
        5

    ]


    supplier_name_by_id = {

        str(supplier.id):
        supplier.name

        for supplier in suppliers

    }


    formula_by_id = {

        formula.id:
        formula

        for formula in formulas

    }


    product_name_by_id = {

        product.id:
        product.name

        for product in products

    }


    raw_material_name_by_id = {

        material.id:
        material.name

        for material in raw_materials

    }


    recent_sales = sorted(

        sales,

        key=lambda sale: (

            normalized_date(
                sale.date
            ),

            sale.id or 0

        ),

        reverse=True

    )[:5]


    recent_purchases = sorted(

        purchases,

        key=lambda purchase: (

            normalized_date(
                purchase.date
            ),

            purchase.id or 0

        ),

        reverse=True

    )[:5]


    recent_lots = sorted(

        lots,

        key=lambda lot: (

            normalized_date(
                lot.production_date
            ),

            lot.id or 0

        ),

        reverse=True

    )[:5]


    recent_lots_data = []

    for lot in recent_lots:

        formula = formula_by_id.get(
            lot.formula_id
        )

        product_name = None

        if formula:

            if str(
                getattr(
                    formula,
                    "output_type",
                    "PRODUCT"
                )
                or
                "PRODUCT"
            ).upper() == "RAW_MATERIAL":

                product_name = raw_material_name_by_id.get(
                    formula.output_raw_material_id
                )

            else:

                product_name = product_name_by_id.get(
                    formula.output_product_id
                )

        recent_lots_data.append({

            "id":
            lot.id,

            "lot_number":
            lot.lot_number,

            "production_date":
            normalized_date(
                lot.production_date
            ),

            "product_name":
            product_name,

            "units_produced":
            numeric(
                lot.units_produced
            ),

            "total_cost":
            numeric(
                lot.total_cost
            )

        })


    sales_total = sum(

        numeric(
            sale.total
        )

        for sale in sales

    )


    sales_month = sum(

        numeric(
            sale.total
        )

        for sale in sales_month_list

    )


    purchases_month = sum(

        numeric(
            purchase.total
        )

        for purchase
        in purchases_month_list

    )


    production_units_month = sum(

        numeric(
            lot.units_produced
        )

        for lot in lots_month_list

    )


    costs_and_expenses_month = (
        costs_month
        +
        expenses_month
    )


    result_month = (
        income_month
        -
        costs_and_expenses_month
    )


    stock_alerts_total = (

        len(
            raw_material_alerts
        )

        +

        len(
            product_alerts
        )

    )


    return {

        # ==========================
        # CAMPOS DEL DASHBOARD ACTUAL
        # ==========================

        "period":
        period,

        "sales_total":
        round(
            sales_total,
            2
        ),

        "sales_month":
        round(
            sales_month,
            2
        ),

        "sales_count_month":
        len(
            sales_month_list
        ),

        "purchases_month":
        round(
            purchases_month,
            2
        ),

        "purchases_count_month":
        len(
            purchases_month_list
        ),

        "income_month":
        round(
            income_month,
            2
        ),

        "costs_month":
        round(
            costs_month,
            2
        ),

        "expenses_month":
        round(
            expenses_month,
            2
        ),

        "costs_and_expenses_month":
        round(
            costs_and_expenses_month,
            2
        ),

        "result_month":
        round(
            result_month,
            2
        ),

        "production_lots_month":
        len(
            lots_month_list
        ),

        "production_units_month":
        round(
            production_units_month,
            2
        ),

        "stock_alerts_total":
        stock_alerts_total,

        "raw_material_alerts":
        raw_material_alerts,

        "product_alerts":
        product_alerts,

        "recent_sales": [

            {

                "id":
                sale.id,

                "number":
                sale.number,

                "client":
                sale.client,

                "date":
                normalized_date(
                    sale.date
                ),

                "payment_method":
                sale.payment_method,

                "total":
                numeric(
                    sale.total
                )

            }

            for sale in recent_sales

        ],

        "recent_purchases": [

            {

                "id":
                purchase.id,

                "number":
                purchase.number,

                "supplier":
                supplier_name_by_id.get(
                    str(
                        purchase.supplier
                    ),
                    purchase.supplier
                ),

                "date":
                normalized_date(
                    purchase.date
                ),

                "payment_method":
                purchase.payment_method,

                "total":
                numeric(
                    purchase.total
                )

            }

            for purchase in recent_purchases

        ],

        "recent_lots":
        recent_lots_data,


        # ==========================
        # COMPATIBILIDAD CON EL
        # DASHBOARD ANTERIOR
        # ==========================

        "ventas":
        round(
            sales_total,
            2
        ),

        "gastos":
        round(
            costs_and_expenses_month,
            2
        ),

        "ganancia":
        round(
            result_month,
            2
        ),

        "stock_productos":
        round(
            sum(
                numeric(
                    product.stock
                )
                for product in products
            ),
            2
        ),

        "productos_stock_bajo":
        len(
            product_alerts
        )

    }


# ================= FORMULAS =================

@app.get("/formulas")
def get_formulas(
    db: Session = Depends(get_db)
):

    formulas = (
        db.query(Formula)
        .order_by(
            Formula.name.asc()
        )
        .all()
    )

    settings = db.query(Settings).first()

    labor_hour_cost = float(
        settings.labor_hour_cost
        if settings
        else 10000
    )

    for formula in formulas:

        formula_items = (
            db.query(FormulaItem)
            .options(
                joinedload(
                    FormulaItem.raw_material
                )
            )
            .filter(
                FormulaItem.formula_id
                ==
                formula.id
            )
            .all()
        )

        material_cost = sum(
            float(item.quantity or 0)
            *
            float(
                item.raw_material.cost or 0
            )
            for item in formula_items
            if item.raw_material
        )

        labor_cost = (
            float(formula.labor_hours or 0)
            *
            labor_hour_cost
        )

        total_cost = (
            material_cost
            +
            labor_cost
        )

        units_produced = float(
            formula.units_produced or 0
        )

        unit_cost = (
            total_cost / units_produced
            if units_produced > 0
            else 0
        )

        margin = float(
            formula.margin_percent
            if formula.margin_percent is not None
            else 40
        )

        divisor = (
            1
            -
            margin / 100
        )

        suggested_price = (
            unit_cost / divisor
            if divisor > 0
            else 0
        )

        # Se agregan como datos calculados para mostrarlos en el listado
        # sin modificar la fórmula ni guardar valores duplicados.
        formula.unit_cost = round(
            unit_cost,
            2
        )

        formula.suggested_price = round(
            suggested_price,
            2
        )

    return formulas


def validated_formula_margin(
    value
):

    margin = float(
        value
        if value is not None
        else 40
    )

    if margin < 0 or margin >= 100:

        raise ValueError(
            "El margen debe ser mayor o igual a 0 y menor a 100"
        )

    return margin


def resolve_formula_output(
    db,
    data,
    current_formula=None
):

    output_type = str(
        data.get(
            "output_type",
            getattr(
                current_formula,
                "output_type",
                "PRODUCT"
            )
            or
            "PRODUCT"
        )
        or
        "PRODUCT"
    ).strip().upper()

    if output_type in {
        "RAW_MATERIAL",
        "INTERMEDIATE",
        "MATERIA_PRIMA"
    }:

        output_type = "RAW_MATERIAL"

        raw_material_id = data.get(
            "output_raw_material_id",
            getattr(
                current_formula,
                "output_raw_material_id",
                None
            )
        )

        if raw_material_id in {
            None,
            ""
        }:

            raise ValueError(
                "Seleccioná la materia prima elaborada que produce la fórmula"
            )

        raw_material = db.query(RawMaterial).filter(
            RawMaterial.id == int(raw_material_id)
        ).first()

        if not raw_material:

            raise ValueError(
                "La materia prima elaborada seleccionada no existe"
            )

        raw_material.is_intermediate = 1

        return (
            "RAW_MATERIAL",
            None,
            raw_material.id
        )

    output_product_id = data.get(
        "output_product_id",
        getattr(
            current_formula,
            "output_product_id",
            None
        )
    )

    if output_product_id in {
        None,
        ""
    }:

        raise ValueError(
            "Seleccioná el producto terminado que produce la fórmula"
        )

    product = db.query(Product).filter(
        Product.id == int(output_product_id)
    ).first()

    if not product:

        raise ValueError(
            "El producto terminado seleccionado no existe"
        )

    if is_resale_product(product):

        raise ValueError(
            "Los productos de reventa no pueden tener fórmula ni lotes de producción"
        )

    return (
        "PRODUCT",
        product.id,
        None
    )


@app.post("/formulas")
def create_formula(
    data: dict,
    db: Session = Depends(get_db)
):

    try:

        (
            output_type,
            output_product_id,
            output_raw_material_id
        ) = resolve_formula_output(
            db,
            data
        )

        item = Formula(
            name=str(data.get("name", "")).strip(),
            output_product_id=output_product_id,
            output_raw_material_id=output_raw_material_id,
            output_type=output_type,
            batch_size=float(data.get("batch_size", 1) or 1),
            labor_hours=float(data.get("labor_hours", 0) or 0),
            units_produced=float(data.get("units_produced", 1) or 1),
            margin_percent=validated_formula_margin(
                data.get("margin_percent", 40)
            ),
            notes=str(data.get("notes", "") or "")
        )

        if not item.name:

            raise ValueError(
                "El nombre de la fórmula es obligatorio"
            )

        db.add(item)
        db.commit()
        db.refresh(item)

        return item

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo guardar la fórmula: {error}"
        }


@app.put("/formulas/{formula_id}")
def update_formula(
    formula_id: int,
    data: dict,
    db: Session = Depends(get_db)
):

    item = db.query(Formula).filter(
        Formula.id == formula_id
    ).first()

    if not item:

        return {
            "error":
            "Fórmula no encontrada"
        }

    existing_lots = db.query(Lot).filter(
        Lot.formula_id == item.id
    ).count()

    try:

        name = str(
            data.get(
                "name",
                item.name
            )
            or
            ""
        ).strip()

        if not name:

            raise ValueError(
                "El nombre de la fórmula es obligatorio"
            )

        (
            output_type,
            output_product_id,
            output_raw_material_id
        ) = resolve_formula_output(
            db,
            data,
            current_formula=item
        )

        current_type = str(
            item.output_type
            or
            "PRODUCT"
        ).upper()

        current_output_id = (
            item.output_raw_material_id
            if current_type == "RAW_MATERIAL"
            else
            item.output_product_id
        )

        new_output_id = (
            output_raw_material_id
            if output_type == "RAW_MATERIAL"
            else
            output_product_id
        )

        if (
            existing_lots > 0
            and
            (
                current_type != output_type
                or
                current_output_id != new_output_id
            )
        ):

            raise ValueError(
                "No se puede cambiar el resultado de una fórmula que ya tiene lotes"
            )

        item.name = name
        item.output_type = output_type
        item.output_product_id = output_product_id
        item.output_raw_material_id = output_raw_material_id
        item.batch_size = float(
            data.get(
                "batch_size",
                item.batch_size
            )
            or
            1
        )
        item.labor_hours = float(
            data.get(
                "labor_hours",
                item.labor_hours
            )
            or
            0
        )
        item.units_produced = float(
            data.get(
                "units_produced",
                item.units_produced
            )
            or
            1
        )
        item.margin_percent = validated_formula_margin(
            data.get(
                "margin_percent",
                item.margin_percent
            )
        )
        item.notes = str(
            data.get(
                "notes",
                item.notes
            )
            or
            ""
        )

        db.commit()
        db.refresh(item)

        return item

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo modificar la fórmula: {error}"
        }


@app.delete("/formulas/{formula_id}")
def delete_formula(
    formula_id: int,
    db: Session = Depends(get_db)
):

    item = db.query(Formula).filter(
        Formula.id == formula_id
    ).first()

    if not item:

        return {
            "error":
            "Fórmula no encontrada"
        }

    lot_count = db.query(Lot).filter(
        Lot.formula_id == item.id
    ).count()

    if lot_count:

        return {
            "error":
            (
                f"No se puede eliminar la fórmula {item.name} porque "
                f"todavía tiene {lot_count} lote(s) asociado(s). "
                "Eliminá primero esos lotes."
            )
        }

    try:

        formula_name = item.name

        db.query(FormulaItem).filter(
            FormulaItem.formula_id == formula_id
        ).delete(
            synchronize_session=False
        )

        db.delete(item)
        db.commit()

        return {
            "message":
            f"Fórmula {formula_name} eliminada correctamente",
            "accounting_unchanged": True
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo eliminar la fórmula: {error}"
        }

@app.get("/formulas/{formula_id}/items")
def get_formula_items(
    formula_id: int,
    db: Session = Depends(get_db)
):

    items = (
        db.query(FormulaItem)
        .join(
            RawMaterial,
            FormulaItem.raw_material_id
            ==
            RawMaterial.id
        )
        .filter(
            FormulaItem.formula_id
            ==
            formula_id
        )
        .order_by(
            RawMaterial.name.asc()
        )
        .all()
    )


    resultado = []


    for item in items:

        material = item.raw_material


        resultado.append({

            "id": item.id,

            "raw_material_id": material.id,

            "raw_material": material.name,

            "quantity": item.quantity,

            "unit": material.unit,

            "unit_cost": material.cost,

            "stock": material.stock,

            "total_cost": item.quantity * material.cost

        })


    return resultado

# ================= LOTES =================

def formula_output_data(
    db,
    formula
):

    output_type = str(
        getattr(
            formula,
            "output_type",
            "PRODUCT"
        )
        or
        "PRODUCT"
    ).upper()

    if (
        output_type == "RAW_MATERIAL"
        or
        getattr(
            formula,
            "output_raw_material_id",
            None
        )
    ):

        raw = db.query(RawMaterial).filter(
            RawMaterial.id == formula.output_raw_material_id
        ).first()

        if not raw:

            raise ValueError(
                "La fórmula no tiene una materia prima elaborada válida"
            )

        return (
            "RAW_MATERIAL",
            raw
        )

    product = db.query(Product).filter(
        Product.id == formula.output_product_id
    ).first()

    if not product:

        raise ValueError(
            "La fórmula no tiene un producto terminado válido"
        )

    return (
        "PRODUCT",
        product
    )


def recalculate_intermediate_material_cost(
    db,
    raw_material_id
):

    raw = db.query(RawMaterial).filter(
        RawMaterial.id == raw_material_id
    ).first()

    if not raw or not int(
        raw.is_intermediate or 0
    ):

        return

    stock = max(
        float(raw.stock or 0),
        0
    )

    if stock <= 0.000001:

        return

    source_lots = db.query(Lot).filter(
        Lot.output_type == "RAW_MATERIAL",
        Lot.output_raw_material_id == raw.id,
        Lot.remaining_units > 0
    ).all()

    lot_quantity = sum(
        float(lot.remaining_units or 0)
        for lot in source_lots
    )

    lot_value = sum(
        float(lot.remaining_units or 0)
        *
        get_inventory_unit_cost(lot)
        for lot in source_lots
    )

    external_quantity = max(
        stock - lot_quantity,
        0
    )

    external_value = (
        external_quantity
        *
        float(raw.cost or 0)
    )

    if lot_quantity > 0:

        raw.cost = (
            lot_value
            +
            external_value
        ) / stock


def restore_lot_material_consumption(
    db,
    lot_id,
    restore_ratio=1.0
):

    # Para lotes antiguos parcialmente consumidos, se repone únicamente
    # la proporción de materias primas correspondiente al saldo que todavía
    # estaba disponible. Esto evita inflar el stock al borrar el historial.
    restore_ratio = min(
        max(
            float(restore_ratio or 0),
            0
        ),
        1
    )

    affected_intermediate_ids = set()

    allocations = db.query(
        LotMaterialSourceAllocation
    ).filter(
        LotMaterialSourceAllocation.consumer_lot_id == lot_id
    ).all()

    for allocation in allocations:

        source_lot = db.query(Lot).filter(
            Lot.id == allocation.source_lot_id
        ).first()

        if source_lot:

            source_lot.remaining_units = (
                float(source_lot.remaining_units or 0)
                +
                (
                    float(allocation.quantity or 0)
                    *
                    restore_ratio
                )
            )

            source_lot.status = "Disponible"

        affected_intermediate_ids.add(
            allocation.raw_material_id
        )

        db.delete(allocation)

    rows = db.execute(
        text(
            """
            SELECT
                raw_material_id,
                quantity
            FROM lot_materials
            WHERE lot_id = :lot_id
            """
        ),
        {
            "lot_id":
            lot_id
        }
    ).mappings().all()

    for row in rows:

        raw = db.query(RawMaterial).filter(
            RawMaterial.id == row["raw_material_id"]
        ).first()

        if raw:

            raw.stock = (
                float(raw.stock or 0)
                +
                (
                    float(row["quantity"] or 0)
                    *
                    restore_ratio
                )
            )

            if int(raw.is_intermediate or 0):

                affected_intermediate_ids.add(
                    raw.id
                )

    db.execute(
        text(
            "DELETE FROM lot_materials WHERE lot_id = :lot_id"
        ),
        {
            "lot_id":
            lot_id
        }
    )

    db.flush()

    for raw_material_id in affected_intermediate_ids:

        recalculate_intermediate_material_cost(
            db,
            raw_material_id
        )


def consume_materials_for_lot(
    db,
    consumer_lot,
    materials_data,
    output_raw_material_id=None
):

    if not isinstance(
        materials_data,
        list
    ) or not materials_data:

        raise ValueError(
            "Agregá al menos una materia prima al lote"
        )

    # Se agrupan cantidades repetidas. Esto permite recibir tanto los
    # ingredientes originales de la fórmula como ingredientes extra.
    quantities_by_material = {}

    for material_data in materials_data:

        try:

            raw_material_id = int(
                material_data.get(
                    "raw_material_id"
                )
            )

            quantity_used = float(
                material_data.get(
                    "real_quantity",
                    material_data.get(
                        "quantity",
                        0
                    )
                )
                or
                0
            )

        except (
            TypeError,
            ValueError
        ) as error:

            raise ValueError(
                "Hay una materia prima o una cantidad inválida"
            ) from error

        if quantity_used < 0:

            raise ValueError(
                "Las cantidades usadas no pueden ser negativas"
            )

        quantities_by_material[raw_material_id] = (
            quantities_by_material.get(
                raw_material_id,
                0
            )
            +
            quantity_used
        )

    if not any(
        quantity > 0
        for quantity in quantities_by_material.values()
    ):

        raise ValueError(
            "Al menos una materia prima debe tener una cantidad mayor a cero"
        )

    material_cost = 0
    affected_intermediate_ids = set()

    for raw_material_id, quantity_used in (
        quantities_by_material.items()
    ):

        raw = (
            db.query(RawMaterial)
            .filter(
                RawMaterial.id == raw_material_id
            )
            .with_for_update()
            .first()
        )

        if not raw:

            raise ValueError(
                "Una de las materias primas no existe"
            )

        if (
            output_raw_material_id
            and
            raw.id == output_raw_material_id
        ):

            raise ValueError(
                "Una materia prima elaborada no puede usarse a sí misma como ingrediente"
            )

        # Una cantidad 0 representa un ingrediente omitido en este lote.
        # Se guarda en el historial, pero no descuenta stock ni suma costo.
        if quantity_used == 0:

            db.execute(
                text(
                    """
                    INSERT INTO lot_materials (
                        lot_id,
                        raw_material_id,
                        quantity,
                        unit_cost,
                        subtotal_cost,
                        source
                    )
                    VALUES (
                        :lot_id,
                        :raw_material_id,
                        0,
                        :unit_cost,
                        0,
                        'REAL'
                    )
                    """
                ),
                {
                    "lot_id":
                    consumer_lot.id,

                    "raw_material_id":
                    raw.id,

                    "unit_cost":
                    float(raw.cost or 0)
                }
            )

            continue

        if (
            float(raw.stock or 0)
            +
            0.000001
            <
            quantity_used
        ):

            raise ValueError(
                (
                    f"Stock insuficiente de {raw.name}. "
                    f"Disponible: {float(raw.stock or 0):.2f}"
                )
            )

        quantity_to_allocate = quantity_used
        subtotal_cost = 0

        if int(raw.is_intermediate or 0):

            source_lots = (
                db.query(Lot)
                .filter(
                    Lot.output_type == "RAW_MATERIAL",
                    Lot.output_raw_material_id == raw.id,
                    Lot.remaining_units > 0
                )
                .order_by(
                    Lot.production_date.asc(),
                    Lot.id.asc()
                )
                .with_for_update()
                .all()
            )

            for source_lot in source_lots:

                available = float(
                    source_lot.remaining_units or 0
                )

                allocated = min(
                    available,
                    quantity_to_allocate
                )

                if allocated <= 0:

                    continue

                unit_cost = get_inventory_unit_cost(
                    source_lot
                )

                allocation_cost = (
                    allocated
                    *
                    unit_cost
                )

                db.add(
                    LotMaterialSourceAllocation(
                        consumer_lot_id=consumer_lot.id,
                        raw_material_id=raw.id,
                        source_lot_id=source_lot.id,
                        quantity=allocated,
                        unit_cost=unit_cost,
                        subtotal_cost=allocation_cost
                    )
                )

                source_lot.remaining_units = (
                    available
                    -
                    allocated
                )

                source_lot.status = (
                    "Disponible"
                    if source_lot.remaining_units > 0.000001
                    else
                    "Agotado"
                )

                subtotal_cost += allocation_cost
                quantity_to_allocate -= allocated

                if quantity_to_allocate <= 0.000001:

                    break

            affected_intermediate_ids.add(
                raw.id
            )

        if quantity_to_allocate > 0.000001:

            subtotal_cost += (
                quantity_to_allocate
                *
                float(raw.cost or 0)
            )

        unit_material_cost = (
            subtotal_cost / quantity_used
            if quantity_used > 0
            else 0
        )

        raw.stock = (
            float(raw.stock or 0)
            -
            quantity_used
        )

        db.execute(
            text(
                """
                INSERT INTO lot_materials (
                    lot_id,
                    raw_material_id,
                    quantity,
                    unit_cost,
                    subtotal_cost,
                    source
                )
                VALUES (
                    :lot_id,
                    :raw_material_id,
                    :quantity,
                    :unit_cost,
                    :subtotal_cost,
                    'REAL'
                )
                """
            ),
            {
                "lot_id":
                consumer_lot.id,

                "raw_material_id":
                raw.id,

                "quantity":
                quantity_used,

                "unit_cost":
                unit_material_cost,

                "subtotal_cost":
                subtotal_cost
            }
        )

        material_cost += subtotal_cost

    db.flush()

    for raw_material_id in affected_intermediate_ids:

        recalculate_intermediate_material_cost(
            db,
            raw_material_id
        )

    return material_cost


def replace_lot_production_journal(
    db,
    lot,
    output_type
):

    db.query(JournalEntry).filter(
        JournalEntry.origin == "PRODUCCION",
        JournalEntry.origin_id == lot.id
    ).delete(
        synchronize_session=False
    )

    db.query(JournalEntry).filter(
        JournalEntry.origin_id.is_(None),
        JournalEntry.concept == f"Producción lote {lot.lot_number}"
    ).delete(
        synchronize_session=False
    )

    concept = f"Producción lote {lot.lot_number}"
    production_date = str(lot.production_date)[:10]

    if output_type == "RAW_MATERIAL":

        # Los insumos y el intermedio pertenecen a Materia Prima, por lo que
        # el traspaso de materiales no cambia el total de esa cuenta. La mano
        # de obra sí se incorpora al valor del intermedio para no reconocerla
        # dos veces: primero como gasto y luego dentro del costo de venta.
        material_cost = float(lot.material_cost or 0)
        labor_cost = float(lot.labor_cost or 0)

        # El oleato/intermedio sigue siendo Materia Prima.
        # Registramos la transformación para que el lote tenga trazabilidad
        # contable aun cuando la mano de obra sea 0. El movimiento neto de
        # Materia Prima es cero porque salen insumos y entra el intermedio.
        if material_cost > 0:

            registrar_asiento(
                db=db,
                fecha=production_date,
                concepto=concept,
                debe_codigo="1.2.01",
                debe_nombre="Materia Prima",
                haber_codigo="1.2.01",
                haber_nombre="Materia Prima",
                importe=material_cost,
                origin="PRODUCCION",
                origin_id=lot.id
            )

        if labor_cost > 0:

            registrar_asiento(
                db=db,
                fecha=production_date,
                concepto=concept,
                debe_codigo="1.2.01",
                debe_nombre="Materia Prima",
                haber_codigo="2.1.02",
                haber_nombre="Sueldos a Pagar",
                importe=labor_cost,
                origin="PRODUCCION",
                origin_id=lot.id
            )

        return

    registrar_asiento_produccion(
        db=db,
        fecha=production_date,
        concepto=concept,
        costo_materiales=float(lot.material_cost or 0),
        costo_mano_obra=float(lot.labor_cost or 0),
        origin_id=lot.id
    )


@app.get("/lots")
def get_lots(
    db: Session = Depends(get_db)
):

    lots = (
        db.query(Lot)
        .order_by(
            Lot.production_date.desc(),
            Lot.id.desc()
        )
        .all()
    )

    formulas = db.query(Formula).all()
    products = db.query(Product).all()
    raw_materials = db.query(RawMaterial).all()

    formula_by_id = {
        formula.id: formula
        for formula in formulas
    }

    product_name_by_id = {
        product.id: product.name
        for product in products
    }

    raw_name_by_id = {
        material.id: material.name
        for material in raw_materials
    }

    material_rows = db.execute(
        text(
            """
            SELECT
                lot_materials.lot_id,
                lot_materials.raw_material_id,
                raw_materials.name,
                raw_materials.unit,
                lot_materials.quantity,
                lot_materials.unit_cost,
                lot_materials.subtotal_cost,
                lot_materials.source
            FROM lot_materials
            LEFT JOIN raw_materials
                ON raw_materials.id = lot_materials.raw_material_id
            ORDER BY
                lot_materials.lot_id,
                raw_materials.name
            """
        )
    ).mappings().all()

    materials_by_lot = {}

    for row in material_rows:

        materials_by_lot.setdefault(
            row["lot_id"],
            []
        ).append({
            "raw_material_id": row["raw_material_id"],
            "name": row["name"] or "Materia prima eliminada",
            "unit": row["unit"] or "",
            "quantity": float(row["quantity"] or 0),
            "real_quantity": float(row["quantity"] or 0),
            "unit_cost": float(row["unit_cost"] or 0),
            "subtotal_cost": float(row["subtotal_cost"] or 0),
            "source": row["source"] or "REAL"
        })

    sale_lot_ids = {
        row[0]
        for row in db.query(
            SaleLotAllocation.lot_id
        ).distinct().all()
    }

    stock_lot_ids = {
        row[0]
        for row in db.query(
            StockMovementLotAllocation.lot_id
        ).distinct().all()
    }

    intermediate_source_lot_ids = {
        row[0]
        for row in db.query(
            LotMaterialSourceAllocation.source_lot_id
        ).distinct().all()
    }

    result = []

    for lot in lots:

        formula = formula_by_id.get(
            lot.formula_id
        )

        output_type = str(
            lot.output_type
            or
            getattr(
                formula,
                "output_type",
                "PRODUCT"
            )
            or
            "PRODUCT"
        ).upper()

        product_id = (
            formula.output_product_id
            if formula and output_type == "PRODUCT"
            else None
        )

        output_raw_material_id = (
            lot.output_raw_material_id
            or
            (
                formula.output_raw_material_id
                if formula
                else None
            )
        )

        materials = materials_by_lot.get(
            lot.id,
            []
        )

        has_estimated_materials = any(
            material["source"] == "FORMULA_ESTIMATE"
            for material in materials
        )

        units_produced = float(
            lot.units_produced or 0
        )

        remaining_units = float(
            lot.remaining_units
            if lot.remaining_units is not None
            else units_produced
        )

        has_sale_allocations = (
            lot.id in sale_lot_ids
        )

        has_stock_allocations = (
            lot.id in stock_lot_ids
        )

        used_as_intermediate_source = (
            lot.id in intermediate_source_lot_ids
        )

        has_balance_difference = (
            abs(
                remaining_units - units_produced
            ) > 0.000001
        )

        has_consumption = (
            has_sale_allocations
            or
            has_stock_allocations
            or
            used_as_intermediate_source
            or
            has_balance_difference
        )

        is_production_lot = (
            (lot.origin or "PRODUCTION") == "PRODUCTION"
        )

        # MODO TEMPORAL DE LIMPIEZA:
        # todos los lotes pueden eliminarse aunque estén vinculados a ventas,
        # movimientos de stock, ajustes u otros lotes. El endpoint elimina
        # solamente los vínculos técnicos necesarios y no toca la contabilidad.
        can_delete = True
        delete_block_reason = ""

        result.append({
            "id": lot.id,
            "lot_number": lot.lot_number,
            "formula_id": lot.formula_id,
            "formula_name": (
                formula.name
                if formula
                else "Fórmula eliminada"
            ),
            "output_type": output_type,
            "origin": lot.origin or "PRODUCTION",
            "product_id": product_id,
            "product_name": (
                product_name_by_id.get(
                    product_id,
                    "Producto sin identificar"
                )
                if output_type == "PRODUCT"
                else raw_name_by_id.get(
                    output_raw_material_id,
                    "Materia prima elaborada sin identificar"
                )
            ),
            "output_raw_material_id": output_raw_material_id,
            "output_raw_material_name": raw_name_by_id.get(
                output_raw_material_id,
                ""
            ),
            "production_date": str(lot.production_date or "")[:10],
            "expiration_date": str(lot.expiration_date or "")[:10],
            "units_produced": units_produced,
            "remaining_units": remaining_units,
            "real_labor_hours": float(lot.real_labor_hours or 0),
            "material_cost": float(lot.material_cost or 0),
            "labor_cost": float(lot.labor_cost or 0),
            "total_cost": float(lot.total_cost or 0),
            "unit_cost": float(lot.unit_cost or 0),
            "inventory_unit_cost": get_inventory_unit_cost(lot),
            "notes": lot.notes or "",
            "status": (
                lot.status
                or
                (
                    "Disponible"
                    if remaining_units > 0
                    else "Agotado"
                )
            ),
            "materials": materials,
            "material_history_source": (
                "FORMULA_ESTIMATE"
                if has_estimated_materials
                else "REAL"
            ),
            "has_sales": has_sale_allocations,
            "has_stock_movements": has_stock_allocations,
            "used_as_intermediate_source": used_as_intermediate_source,
            "has_consumption": has_consumption,
            "has_balance_difference": has_balance_difference,
            "can_edit": is_production_lot,
            "can_delete": can_delete,
            "delete_block_reason": delete_block_reason
        })

    return result


@app.put("/lots/{lot_id}")
def update_lot(
    lot_id: int,
    data: dict,
    db: Session = Depends(get_db)
):

    lot = (
        db.query(Lot)
        .filter(
            Lot.id == lot_id
        )
        .with_for_update()
        .first()
    )

    if not lot:

        return {
            "error":
            "Lote no encontrado"
        }

    if (lot.origin or "PRODUCTION") != "PRODUCTION":

        return {
            "error":
            "Los lotes generados por ajustes de stock no se editan desde Producción"
        }

    formula = db.query(Formula).filter(
        Formula.id == lot.formula_id
    ).first()

    if not formula:

        return {
            "error":
            "No se encontró la fórmula del lote"
        }

    try:

        output_type, output_item = formula_output_data(
            db,
            formula
        )

        old_units = float(
            lot.units_produced or 0
        )

        old_remaining = float(
            lot.remaining_units
            if lot.remaining_units is not None
            else old_units
        )

        consumed_units = max(
            old_units - old_remaining,
            0
        )

        new_units = float(
            data.get(
                "units_produced",
                old_units
            )
            or
            0
        )

        if new_units <= 0:

            raise ValueError(
                "Las unidades producidas deben ser mayores a cero"
            )

        if new_units + 0.000001 < consumed_units:

            raise ValueError(
                (
                    f"El lote ya tiene {consumed_units:.2f} unidades utilizadas. "
                    "No puede reducirse por debajo de esa cantidad."
                )
            )

        unit_delta = new_units - old_units

        if output_type == "PRODUCT":

            if (
                unit_delta < 0
                and
                float(output_item.stock or 0)
                +
                0.000001
                <
                abs(unit_delta)
            ):

                raise ValueError(
                    "El stock actual del producto no alcanza para reducir el lote"
                )

            output_item.stock = (
                float(output_item.stock or 0)
                +
                unit_delta
            )

        else:

            if (
                unit_delta < 0
                and
                float(output_item.stock or 0)
                +
                0.000001
                <
                abs(unit_delta)
            ):

                raise ValueError(
                    "El stock actual del intermedio no alcanza para reducir el lote"
                )

            output_item.stock = (
                float(output_item.stock or 0)
                +
                unit_delta
            )

        lot.units_produced = new_units
        lot.remaining_units = max(
            old_remaining + unit_delta,
            0
        )

        lot.production_date = parse_date_value(
            data.get(
                "production_date",
                lot.production_date
            ),
            "fecha de elaboración"
        )

        lot.expiration_date = parse_date_value(
            data.get(
                "expiration_date",
                lot.expiration_date
            ),
            "fecha de vencimiento",
            allow_none=True
        )

        lot.notes = str(
            data.get(
                "notes",
                lot.notes or ""
            )
            or
            ""
        )

        previous_labor_hours = float(
            lot.real_labor_hours or 0
        )

        previous_labor_cost = float(
            lot.labor_cost or 0
        )

        labor_hours_changed = (
            "real_labor_hours" in data
        )

        lot.real_labor_hours = float(
            data.get(
                "real_labor_hours",
                previous_labor_hours
            )
            or
            0
        )

        if lot.real_labor_hours < 0:

            raise ValueError(
                "Las horas de trabajo no pueden ser negativas"
            )

        if "materials" in data:

            existing_sources = db.execute(
                text(
                    """
                    SELECT source
                    FROM lot_materials
                    WHERE lot_id = :lot_id
                    """
                ),
                {
                    "lot_id":
                    lot.id
                }
            ).mappings().all()

            if any(
                row["source"] == "FORMULA_ESTIMATE"
                for row in existing_sources
            ):

                raise ValueError(
                    "Este lote es anterior al historial detallado y sus materias primas no pueden editarse"
                )

            restore_lot_material_consumption(
                db,
                lot.id
            )

            material_cost = consume_materials_for_lot(
                db=db,
                consumer_lot=lot,
                materials_data=data.get("materials", []),
                output_raw_material_id=(
                    output_item.id
                    if output_type == "RAW_MATERIAL"
                    else None
                )
            )

        else:

            material_cost = float(
                lot.material_cost or 0
            )

        if labor_hours_changed:

            settings = db.query(Settings).first()

            historical_labor_hour_cost = (
                previous_labor_cost
                /
                previous_labor_hours
                if previous_labor_hours > 0
                else
                float(
                    settings.labor_hour_cost
                    if settings
                    else 10000
                )
            )

            labor_cost = (
                float(lot.real_labor_hours or 0)
                *
                historical_labor_hour_cost
            )

        else:

            # Corregir la fecha, el vencimiento, las unidades o las notas no
            # debe volver a valuar la mano de obra con el valor actual.
            labor_cost = previous_labor_cost

        total_cost = (
            material_cost
            +
            labor_cost
        )

        lot.output_type = output_type
        lot.output_raw_material_id = (
            output_item.id
            if output_type == "RAW_MATERIAL"
            else None
        )
        lot.material_cost = material_cost
        lot.labor_cost = labor_cost
        lot.total_cost = total_cost
        lot.unit_cost = total_cost / new_units
        lot.inventory_unit_cost = (
            total_cost / new_units
            if output_type == "RAW_MATERIAL"
            else material_cost / new_units
        )
        lot.status = (
            "Disponible"
            if float(lot.remaining_units or 0) > 0.000001
            else "Agotado"
        )

        if output_type == "RAW_MATERIAL":

            recalculate_intermediate_material_cost(
                db,
                output_item.id
            )

        replace_lot_production_journal(
            db,
            lot,
            output_type
        )

        db.commit()
        db.refresh(lot)

        return {
            "message":
            f"Lote {lot.lot_number} modificado correctamente",
            "id": lot.id,
            "units_produced": float(lot.units_produced or 0),
            "remaining_units": float(lot.remaining_units or 0),
            "total_cost": round(float(lot.total_cost or 0), 2),
            "unit_cost": round(float(lot.unit_cost or 0), 2)
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo modificar el lote: {error}"
        }


@app.delete("/lots/{lot_id}")
def delete_lot(
    lot_id: int,
    db: Session = Depends(get_db)
):

    lot = db.query(Lot).filter(
        Lot.id == lot_id
    ).first()

    if not lot:

        return {
            "error":
            "Lote no encontrado"
        }

    try:

        # MODO TEMPORAL DE LIMPIEZA NEUTRA:
        # se elimina el lote de prueba sin modificar stock de productos,
        # materias primas, costos ni asientos contables.
        # Solo se quitan las referencias técnicas necesarias para que
        # PostgreSQL permita borrar el registro.

        deleted_sale_links = (
            db.query(SaleLotAllocation)
            .filter(
                SaleLotAllocation.lot_id == lot.id
            )
            .delete(
                synchronize_session=False
            )
        )

        deleted_stock_links = (
            db.query(StockMovementLotAllocation)
            .filter(
                StockMovementLotAllocation.lot_id == lot.id
            )
            .delete(
                synchronize_session=False
            )
        )

        deleted_intermediate_source_links = (
            db.query(LotMaterialSourceAllocation)
            .filter(
                LotMaterialSourceAllocation.source_lot_id == lot.id
            )
            .delete(
                synchronize_session=False
            )
        )

        deleted_intermediate_consumer_links = (
            db.query(LotMaterialSourceAllocation)
            .filter(
                LotMaterialSourceAllocation.consumer_lot_id == lot.id
            )
            .delete(
                synchronize_session=False
            )
        )

        db.execute(
            text(
                "DELETE FROM lot_materials WHERE lot_id = :lot_id"
            ),
            {
                "lot_id":
                lot.id
            }
        )

        lot_number = lot.lot_number

        db.delete(lot)
        db.flush()
        db.commit()

        removed_links = (
            int(deleted_sale_links or 0)
            +
            int(deleted_stock_links or 0)
            +
            int(deleted_intermediate_source_links or 0)
            +
            int(deleted_intermediate_consumer_links or 0)
        )

        warning_parts = [
            "No se descontó stock de productos ni se repusieron materias primas.",
            "Los asientos contables no fueron modificados."
        ]

        if removed_links:

            warning_parts.insert(
                0,
                "Se quitaron "
                f"{removed_links} vínculos técnicos con ventas, movimientos "
                "u otros lotes. Esos registros permanecen guardados."
            )

        return {
            "message":
            f"Lote {lot_number} eliminado correctamente",
            "stock_unchanged": True,
            "materials_unchanged": True,
            "accounting_unchanged": True,
            "temporary_cleanup_mode": True,
            "removed_sale_links": int(deleted_sale_links or 0),
            "removed_stock_links": int(deleted_stock_links or 0),
            "removed_intermediate_links": (
                int(deleted_intermediate_source_links or 0)
                +
                int(deleted_intermediate_consumer_links or 0)
            ),
            "warning": " ".join(warning_parts)
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo eliminar el lote: {error}"
        }


@app.post("/lots")
def create_lot(
    lot: dict,
    db: Session = Depends(get_db)
):

    try:

        units_produced = float(
            lot.get(
                "units_produced",
                0
            )
            or
            0
        )

        real_labor_hours = float(
            lot.get(
                "real_labor_hours",
                0
            )
            or
            0
        )

        if units_produced <= 0:

            raise ValueError(
                "Las unidades producidas deben ser mayores a cero"
            )

        formula = db.query(Formula).filter(
            Formula.id == int(lot["formula_id"])
        ).first()

        if not formula:

            raise ValueError(
                "Fórmula no encontrada"
            )

        output_type, output_item = formula_output_data(
            db,
            formula
        )

        lot_number = take_next_document_number(
            db,
            "LOT"
        )

        item = Lot(
            lot_number=lot_number,
            formula_id=formula.id,
            output_type=output_type,
            output_raw_material_id=(
                output_item.id
                if output_type == "RAW_MATERIAL"
                else None
            ),
            origin="PRODUCTION",
            production_date=parse_date_value(
                lot.get("production_date"),
                "fecha de elaboración"
            ),
            expiration_date=parse_date_value(
                lot.get("expiration_date"),
                "fecha de vencimiento",
                allow_none=True
            ),
            units_produced=units_produced,
            remaining_units=units_produced,
            real_labor_hours=real_labor_hours,
            material_cost=0,
            labor_cost=0,
            total_cost=0,
            unit_cost=0,
            inventory_unit_cost=0,
            notes=lot.get(
                "notes",
                ""
            ),
            status="Disponible"
        )

        db.add(item)
        db.flush()

        material_cost = consume_materials_for_lot(
            db=db,
            consumer_lot=item,
            materials_data=lot.get("materials", []),
            output_raw_material_id=(
                output_item.id
                if output_type == "RAW_MATERIAL"
                else None
            )
        )

        settings = db.query(Settings).first()

        labor_hour_cost = float(
            settings.labor_hour_cost
            if settings
            else 10000
        )

        labor_cost = (
            real_labor_hours
            *
            labor_hour_cost
        )

        total_cost = (
            material_cost
            +
            labor_cost
        )

        full_unit_cost = (
            total_cost
            /
            units_produced
        )

        inventory_unit_cost = (
            full_unit_cost
            if output_type == "RAW_MATERIAL"
            else material_cost / units_produced
        )

        item.material_cost = material_cost
        item.labor_cost = labor_cost
        item.total_cost = total_cost
        item.unit_cost = full_unit_cost
        item.inventory_unit_cost = inventory_unit_cost

        if output_type == "PRODUCT":

            output_item.stock = (
                float(output_item.stock or 0)
                +
                units_produced
            )

        else:

            old_stock = float(
                output_item.stock or 0
            )

            old_value = (
                old_stock
                *
                float(output_item.cost or 0)
            )

            output_item.stock = (
                old_stock
                +
                units_produced
            )

            output_item.cost = (
                old_value
                +
                total_cost
            ) / output_item.stock

            output_item.is_intermediate = 1

        replace_lot_production_journal(
            db,
            item,
            output_type
        )

        db.commit()
        db.refresh(item)

        return {
            "id": item.id,
            "lot_number": item.lot_number,
            "output_type": output_type,
            "material_cost": round(material_cost, 2),
            "labor_cost": round(labor_cost, 2),
            "total_cost": round(total_cost, 2),
            "unit_cost": round(full_unit_cost, 2),
            "inventory_unit_cost": round(inventory_unit_cost, 2),
            "message": (
                "Lote de materia prima elaborada guardado correctamente"
                if output_type == "RAW_MATERIAL"
                else "Lote guardado y contabilizado correctamente"
            )
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo guardar el lote: {error}"
        }


# -------- INGREDIENTES --------

@app.post("/formula-items")
def create_formula_item(
    item: FormulaItemCreate,
    db: Session = Depends(get_db)
):

    ingredient = FormulaItem(
        formula_id=item.formula_id,
        raw_material_id=item.raw_material_id,
        quantity=item.quantity
    )

    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)

    return ingredient


@app.get("/formula-items/{formula_id}")
def get_formula_items(
    formula_id: int,
    db: Session = Depends(get_db)
):

    return (
        db.query(FormulaItem)
        .options(
            joinedload(
                FormulaItem.raw_material
            )
        )
        .join(
            RawMaterial,
            FormulaItem.raw_material_id
            ==
            RawMaterial.id
        )
        .filter(
            FormulaItem.formula_id
            ==
            formula_id
        )
        .order_by(
            RawMaterial.name.asc()
        )
        .all()
    )


@app.delete("/formula-items/{item_id}")
def delete_formula_item(
    item_id: int,
    db: Session = Depends(get_db)
):

    item = db.query(FormulaItem).filter(
        FormulaItem.id == item_id
    ).first()

    if not item:
        return {"error": "Ingrediente no encontrado"}

    db.delete(item)
    db.commit()

    return {"message": "Ingrediente eliminado"}


# -------- COSTO DE FORMULA --------

@app.get("/formula-cost/{formula_id}")
def formula_cost(
    formula_id: int,
    db: Session = Depends(get_db)
):

    formula = db.query(Formula).filter(
        Formula.id == formula_id
    ).first()

    if not formula:
        return {"error": "Formula no encontrada"}

    items = (
        db.query(FormulaItem)
        .options(joinedload(FormulaItem.raw_material))
        .filter(
            FormulaItem.formula_id == formula_id
        )
        .all()
    )

    total_materiales = 0
    detalle = []

    for item in items:

        material = item.raw_material

        if not material:
            continue

        # RawMaterial.cost ya guarda el costo por unidad.
        # No debe volver a dividirse por el stock disponible.
        costo_unitario = float(
            material.cost or 0
        )

        costo_item = (
            costo_unitario
            *
            float(item.quantity or 0)
        )

        total_materiales += costo_item

        detalle.append({
            "material": material.name,
            "cantidad": item.quantity,
            "costo": round(costo_item, 2)
        })

    settings = db.query(Settings).first()

    valor_hora = (
        settings.labor_hour_cost
        if settings
        else 10000
    )

    mano_obra = formula.labor_hours * valor_hora

    costo_total = total_materiales + mano_obra

    costo_unitario = (
        costo_total / formula.units_produced
        if formula.units_produced > 0
        else 0
    )

    margen = float(
        formula.margin_percent
        if formula.margin_percent is not None
        else 40
    )

    divisor = (
        1
        -
        margen / 100
    )

    precio_estimado = (
        costo_unitario / divisor
        if divisor > 0
        else 0
    )

    return {

        "formula_id": formula.id,

        "materias_primas": round(total_materiales, 2),

        "mano_obra": round(mano_obra, 2),

        "horas_trabajo": formula.labor_hours,

        "unidades_producidas": formula.units_produced,

        "costo_total": round(costo_total, 2),

        "costo_unitario": round(costo_unitario, 2),

        "margen_rentabilidad": round(margen, 2),

        "precio_estimado": round(precio_estimado, 2),

        "detalle": detalle

    }
    
   # ================= MATERIAS PRIMAS =================

@app.get("/raw-materials")
def get_raw_materials(
    db: Session = Depends(get_db)
):

    materials = (
        db.query(RawMaterial)
        .order_by(
            RawMaterial.name.asc()
        )
        .all()
    )

    return [
        {
            "id": material.id,
            "code": material.code or "",
            "name": material.name,
            "category": material.category or "",
            "unit": material.unit or "",
            "stock": round(
                float(material.stock or 0),
                2
            ),
            "minimum_stock": round(
                float(material.minimum_stock or 0),
                2
            ),
            "cost": float(material.cost or 0),
            "supplier": material.supplier or "",
            "location": material.location or "",
            "is_intermediate": int(
                material.is_intermediate or 0
            )
        }
        for material in materials
    ]


def normalized_material_name(
    value
):

    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .split()
    )


def ensure_unique_material_name(
    db,
    name,
    exclude_id=None
):

    normalized = normalized_material_name(
        name
    )

    if not normalized:

        raise ValueError(
            "El nombre de la materia prima es obligatorio"
        )

    for existing in db.query(RawMaterial).all():

        if (
            exclude_id is not None
            and
            existing.id == exclude_id
        ):

            continue

        if normalized_material_name(
            existing.name
        ) == normalized:

            raise ValueError(
                "Ya existe una materia prima con ese nombre"
            )


@app.post("/raw-materials")
def create_raw_material(
    material: RawMaterialCreate,
    db: Session = Depends(get_db)
):

    try:

        ensure_unique_material_name(
            db,
            material.name
        )

        internal_code = str(
            material.code or ""
        ).strip()

        if not internal_code:

            internal_code = (
                "RM-"
                +
                uuid4().hex[:10].upper()
            )

        item = RawMaterial(
            code=internal_code,
            name=str(material.name).strip(),
            category=material.category,
            unit=material.unit,
            stock=material.stock,
            minimum_stock=material.minimum_stock,
            cost=material.cost,
            supplier=material.supplier,
            location=material.location,
            is_intermediate=int(
                material.is_intermediate or 0
            )
        )

        db.add(item)
        db.commit()
        db.refresh(item)

        return item

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo guardar la materia prima: {error}"
        }


@app.put("/raw-materials/{material_id}")
def update_raw_material(
    material_id: int,
    material: RawMaterialCreate,
    db: Session = Depends(get_db)
):

    item = db.query(RawMaterial).filter(
        RawMaterial.id == material_id
    ).first()

    if not item:

        return {
            "error":
            "Materia prima no encontrada"
        }

    try:

        ensure_unique_material_name(
            db,
            material.name,
            exclude_id=item.id
        )

        supplied_code = str(
            material.code or ""
        ).strip()

        if supplied_code:

            item.code = supplied_code

        elif not item.code:

            item.code = (
                "RM-"
                +
                uuid4().hex[:10].upper()
            )

        item.name = str(material.name).strip()
        item.category = material.category
        item.unit = material.unit
        item.stock = material.stock
        item.minimum_stock = material.minimum_stock
        item.cost = material.cost
        item.supplier = material.supplier
        item.location = material.location
        item.is_intermediate = max(
            int(item.is_intermediate or 0),
            int(material.is_intermediate or 0)
        )

        db.commit()
        db.refresh(item)

        return item

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo modificar la materia prima: {error}"
        }


@app.delete("/raw-materials/{material_id}")
def delete_raw_material(
    material_id: int,
    db: Session = Depends(get_db)
):

    item = db.query(RawMaterial).filter(
        RawMaterial.id == material_id
    ).first()

    if not item:
        return {"error": "Materia prima no encontrada"}

    db.delete(item)
    db.commit()

    return {"message": "Materia prima eliminada"}

    # ================= CONFIGURACION =================

@app.get("/settings")
def get_settings(
    db: Session = Depends(get_db)
):

    settings = db.query(Settings).first()

    if not settings:

        settings = Settings()

        db.add(settings)

        db.commit()

        db.refresh(settings)

    return settings


@app.put("/settings")
def update_settings(
    data: dict,
    db: Session = Depends(get_db)
):

    settings = db.query(Settings).first()

    if not settings:

        settings = Settings()

        db.add(settings)

        db.commit()

        db.refresh(settings)

    settings.labor_hour_cost = data["labor_hour_cost"]

    db.commit()

    db.refresh(settings)

    return settings

    # ================= PROVEEDORES =================

@app.get("/suppliers")
def get_suppliers(
    db: Session = Depends(get_db)
):

    return db.query(Supplier).all()

@app.post("/suppliers")
def create_supplier(
    supplier: SupplierCreate,
    db: Session = Depends(get_db)
):

    item = Supplier(
        name=supplier.name,
        business_name=supplier.business_name,
        tax_id=supplier.tax_id,
        phone=supplier.phone,
        email=supplier.email,
        address=supplier.address,
        city=supplier.city,
        province=supplier.province,
        contact=supplier.contact,
        payment_terms=supplier.payment_terms,
        notes=supplier.notes
    )

    db.add(item)

    db.commit()

    db.refresh(item)

    return item

# ================= ENCARGOS / IDEAS =================
from sqlalchemy import text as _notes_text
from datetime import datetime as _notes_datetime


def _ensure_notes_table(db):
    db.execute(
        _notes_text(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                kind VARCHAR DEFAULT 'Nota',
                content TEXT NOT NULL,
                created_at VARCHAR,
                updated_at VARCHAR
            )
            """
        )
    )
    db.commit()


@app.get("/notes")
def get_notes(
    db: Session = Depends(get_db)
):
    _ensure_notes_table(db)

    rows = db.execute(
        _notes_text(
            """
            SELECT
                id,
                kind,
                content,
                created_at,
                updated_at
            FROM notes
            ORDER BY id DESC
            """
        )
    ).mappings().all()

    return [
        {
            "id": row["id"],
            "kind": row["kind"] or "Nota",
            "content": row["content"] or "",
            "created_at": row["created_at"] or "",
            "updated_at": row["updated_at"] or ""
        }
        for row in rows
    ]


@app.post("/notes")
def create_note(
    data: dict,
    db: Session = Depends(get_db)
):
    _ensure_notes_table(db)

    content = str(data.get("content", "") or "").strip()
    kind = str(data.get("kind", "Nota") or "Nota").strip()

    if not content:
        return JSONResponse(
            status_code=400,
            content={"error": "Escribí algo antes de guardar la nota"}
        )

    if kind not in {"Nota", "Idea", "Encargo"}:
        kind = "Nota"

    now = _notes_datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = db.execute(
        _notes_text(
            """
            INSERT INTO notes (
                kind,
                content,
                created_at,
                updated_at
            )
            VALUES (
                :kind,
                :content,
                :created_at,
                :updated_at
            )
            RETURNING
                id,
                kind,
                content,
                created_at,
                updated_at
            """
        ),
        {
            "kind": kind,
            "content": content,
            "created_at": now,
            "updated_at": now
        }
    ).mappings().first()

    db.commit()
    return dict(row)


@app.put("/notes/{note_id}")
def update_note(
    note_id: int,
    data: dict,
    db: Session = Depends(get_db)
):
    _ensure_notes_table(db)

    content = str(data.get("content", "") or "").strip()
    kind = str(data.get("kind", "Nota") or "Nota").strip()

    if not content:
        return JSONResponse(
            status_code=400,
            content={"error": "La nota no puede quedar vacía"}
        )

    if kind not in {"Nota", "Idea", "Encargo"}:
        kind = "Nota"

    now = _notes_datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = db.execute(
        _notes_text(
            """
            UPDATE notes
            SET
                kind = :kind,
                content = :content,
                updated_at = :updated_at
            WHERE id = :note_id
            RETURNING
                id,
                kind,
                content,
                created_at,
                updated_at
            """
        ),
        {
            "note_id": note_id,
            "kind": kind,
            "content": content,
            "updated_at": now
        }
    ).mappings().first()

    if not row:
        db.rollback()
        return JSONResponse(
            status_code=404,
            content={"error": "Nota no encontrada"}
        )

    db.commit()
    return dict(row)


@app.delete("/notes/{note_id}")
def delete_note(
    note_id: int,
    db: Session = Depends(get_db)
):
    _ensure_notes_table(db)

    row = db.execute(
        _notes_text(
            """
            DELETE FROM notes
            WHERE id = :note_id
            RETURNING id
            """
        ),
        {"note_id": note_id}
    ).first()

    if not row:
        db.rollback()
        return JSONResponse(
            status_code=404,
            content={"error": "Nota no encontrada"}
        )

    db.commit()
    return {"message": "Nota eliminada correctamente"}

# ================= COTIZADOR WEB PROVEEDORES =================
# Version 3: coincidencia estricta de producto + variantes estructuradas.
import json as _sq_json
import re as _sq_re
import time as _sq_time
import unicodedata as _sq_unicodedata
import xml.etree.ElementTree as _sq_et
from concurrent.futures import ThreadPoolExecutor as _sq_ThreadPoolExecutor
from html import unescape as _sq_unescape
from urllib.parse import quote as _sq_quote, urljoin as _sq_urljoin, urlparse as _sq_urlparse
from urllib.request import Request as _sq_Request, urlopen as _sq_urlopen

_SQ_PROVIDERS = [
    {
        "name": "Amizcle",
        "base": "https://amizcle.empretienda.com.ar",
        "kind": "empretienda",
        "fallback_paths": ["/productos", "/aceites-naturales", "/insumos-cosmetica"]
    },
    {
        "name": "Ecomarketshop",
        "base": "https://ecomarketshop.empretienda.com.ar",
        "kind": "empretienda",
        "fallback_paths": ["/productos", "/materias-primas"]
    },
    {
        "name": "Parvati",
        "base": "https://www.psyn.com.ar",
        "kind": "tiendanube",
        "fallback_paths": ["/productos/", "/aceites-polvos-mantecas-y-ceras/aceites1/"]
    },
    {
        "name": "Ecosmética",
        "base": "https://ecosmetica.net",
        "kind": "separate_products",
        "fallback_paths": ["/productos/", "/insumos-cosmetica-natural-capilar/aceites-vegetales2/"]
    }
]

_SQ_CACHE = {}
_SQ_SITE_URLS_CACHE = {}
_SQ_CACHE_TTL = 600
_SQ_SITE_CACHE_TTL = 21600

_SQ_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "y", "con", "para",
    "natural", "cosmetico", "cosmetica", "virgen", "puro", "pura",
    "organico", "organica"
}

_SQ_PRODUCT_TYPES = {
    "aceite", "manteca", "arcilla", "cera", "hidrolato", "extracto",
    "esencia", "fragancia", "oleato", "conservante", "vitamina"
}


def _sq_norm(value):
    text = str(value or "").strip().lower()
    text = _sq_unicodedata.normalize("NFD", text)
    text = "".join(
        char for char in text
        if _sq_unicodedata.category(char) != "Mn"
    )
    text = _sq_re.sub(r"[^a-z0-9]+", " ", text)
    return _sq_re.sub(r"\s+", " ", text).strip()


def _sq_tokens(value):
    return [
        token
        for token in _sq_norm(value).split()
        if token and token not in _SQ_STOPWORDS
    ]


def _sq_fetch(url, timeout=10, max_bytes=4_000_000):
    key = ("fetch", url)
    now = _sq_time.time()
    cached = _SQ_CACHE.get(key)

    if cached and now - cached["time"] < _SQ_CACHE_TTL:
        return cached["value"]

    request = _sq_Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; NativaGestion/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9"
        }
    )

    with _sq_urlopen(request, timeout=timeout) as response:
        data = response.read(max_bytes)

    text = data.decode("utf-8", errors="ignore")
    _SQ_CACHE[key] = {"time": now, "value": text}
    return text


def _sq_host(url):
    return (_sq_urlparse(url).hostname or "").lower()


def _sq_same_host(url, base):
    return _sq_host(url) == _sq_host(base)


def _sq_strip_html(html):
    text = _sq_re.sub(
        r"(?is)<(script|style|svg).*?>.*?</\1>",
        " ",
        html or ""
    )
    text = _sq_re.sub(r"(?s)<[^>]+>", " ", text)
    text = _sq_unescape(text)
    return _sq_re.sub(r"\s+", " ", text).strip()


def _sq_extract_title(html):
    for pattern in [
        r'(?is)<h1[^>]*>(.*?)</h1>',
        r'(?is)<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        r'(?is)<title[^>]*>(.*?)</title>'
    ]:
        match = _sq_re.search(pattern, html or "")
        if match:
            value = _sq_strip_html(match.group(1))
            if value:
                return value
    return ""


def _sq_price_number(value):
    if value is None:
        return None

    text = str(value).strip()
    text = _sq_re.sub(r"[^\d,.\-]", "", text)

    if not text:
        return None

    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    elif "." in text:
        left, right = text.rsplit(".", 1)
        if len(right) == 3 and left.replace("-", "").isdigit():
            text = left + right

    try:
        number = float(text)
    except Exception:
        return None

    return number if number > 0 else None


def _sq_convert_size(number_text, unit_text):
    try:
        number = float(
            str(number_text)
            .strip()
            .replace(" ", "")
            .replace(",", ".")
        )
    except Exception:
        return None

    if number <= 0:
        return None

    unit = _sq_norm(unit_text)

    if unit in {"g", "gr", "grs", "gramo", "gramos"}:
        return number, "g"
    if unit in {"kg", "kilo", "kilos"}:
        return number * 1000, "g"
    if unit in {"ml", "cc", "mililitro", "mililitros"}:
        return number, "ml"
    if unit in {"l", "lt", "lts", "litro", "litros"}:
        return number * 1000, "ml"

    return None


def _sq_find_size(text):
    match = _sq_re.search(
        r"(?i)\b([0-9]+(?:[.,][0-9]+)?)\s*(cc|ml|mililitros?|l|litros?|lts?|g|grs?|gramos?|kg|kilos?)\b",
        str(text or "")
    )

    if not match:
        return None

    converted = _sq_convert_size(
        match.group(1),
        match.group(2)
    )

    if not converted:
        return None

    return {
        "quantity": converted[0],
        "unit": converted[1]
    }


def _sq_query_profile(query):
    tokens = set(_sq_tokens(query))
    return {
        "tokens": tokens,
        "types": {
            token for token in tokens
            if token in _SQ_PRODUCT_TYPES
        },
        "core": {
            token for token in tokens
            if token not in _SQ_PRODUCT_TYPES
        }
    }


def _sq_title_acceptable(title, query):
    haystack = _sq_norm(title)
    profile = _sq_query_profile(query)

    if not haystack:
        return False

    # Las palabras que identifican la materia prima tienen que estar.
    # Ej.: "almendras" es obligatoria para evitar "aceite de cannabis".
    if profile["core"]:
        matched_core = {
            token for token in profile["core"]
            if token in haystack
        }

        if not matched_core:
            return False

        if len(profile["core"]) <= 2 and matched_core != profile["core"]:
            return False

    # Si el usuario indicó un tipo, penalizamos/cortamos otro tipo distinto.
    if profile["types"]:
        if not any(product_type in haystack for product_type in profile["types"]):
            return False

        other_types = {
            product_type
            for product_type in _SQ_PRODUCT_TYPES
            if product_type in haystack
            and product_type not in profile["types"]
        }

        if other_types:
            return False

    return True


def _sq_score_text(text, query):
    haystack = _sq_norm(text)
    profile = _sq_query_profile(query)

    if not haystack:
        return -1000

    score = 0

    if _sq_norm(query) in haystack:
        score += 50

    for token in profile["tokens"]:
        if token in haystack:
            score += 10
        else:
            score -= 8

    return score


def _sq_desired_size_bonus(text, requested_unit, desired_quantity):
    if not desired_quantity or desired_quantity <= 0:
        return 0

    size = _sq_find_size(text)

    if not size:
        return 0

    requested = _sq_norm(requested_unit)

    if requested.startswith("ml") and size["unit"] != "ml":
        return -30
    if requested.startswith("g") and size["unit"] != "g":
        return -30

    if abs(size["quantity"] - desired_quantity) < 0.001:
        return 80

    delta = abs(size["quantity"] - desired_quantity) / max(desired_quantity, 1)
    return max(-20, 20 - int(delta * 30))


def _sq_parse_sitemap(xml_text, provider):
    urls = []
    children = []

    try:
        root = _sq_et.fromstring(xml_text)
    except Exception:
        return urls, children

    tag = root.tag.lower()

    if tag.endswith("sitemapindex"):
        for loc in root.findall(".//{*}loc"):
            value = (loc.text or "").strip()
            if value and _sq_same_host(value, provider["base"]):
                children.append(value)

    elif tag.endswith("urlset"):
        for loc in root.findall(".//{*}loc"):
            value = (loc.text or "").strip()
            if value and _sq_same_host(value, provider["base"]):
                urls.append(value)

    return urls, children


def _sq_site_urls(provider):
    key = provider["name"]
    now = _sq_time.time()
    cached = _SQ_SITE_URLS_CACHE.get(key)

    if cached and now - cached["time"] < _SQ_SITE_CACHE_TTL:
        return cached["urls"]

    base = provider["base"].rstrip("/")
    queue = [
        base + "/sitemap.xml",
        base + "/sitemap_index.xml"
    ]

    try:
        robots = _sq_fetch(
            base + "/robots.txt",
            timeout=6,
            max_bytes=200_000
        )

        for match in _sq_re.findall(
            r"(?im)^\s*Sitemap:\s*(\S+)",
            robots
        ):
            if _sq_same_host(match, base):
                queue.insert(0, match)
    except Exception:
        pass

    seen_maps = set()
    urls = []

    while queue and len(seen_maps) < 15:
        sitemap_url = queue.pop(0)

        if sitemap_url in seen_maps:
            continue

        seen_maps.add(sitemap_url)

        try:
            xml_text = _sq_fetch(
                sitemap_url,
                timeout=7,
                max_bytes=4_000_000
            )
        except Exception:
            continue

        found_urls, child_maps = _sq_parse_sitemap(
            xml_text,
            provider
        )

        urls.extend(found_urls)

        for child in child_maps:
            if child not in seen_maps:
                queue.append(child)

    result = []
    seen = set()

    for url in urls:
        clean = url.split("#", 1)[0]
        if clean not in seen:
            seen.add(clean)
            result.append(clean)

    _SQ_SITE_URLS_CACHE[key] = {
        "time": now,
        "urls": result
    }

    return result


def _sq_extract_links(html, current_url, provider, query):
    found = []

    for href, inner in _sq_re.findall(
        r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html or ""
    ):
        url = _sq_urljoin(current_url, _sq_unescape(href).strip())

        if not url.startswith(("http://", "https://")):
            continue
        if not _sq_same_host(url, provider["base"]):
            continue

        label = _sq_strip_html(inner)
        score = max(
            _sq_score_text(label, query),
            _sq_score_text(url, query)
        )

        if score > 0:
            found.append({
                "url": url.split("#", 1)[0],
                "score": score
            })

    return found


def _sq_candidate_urls(
    provider,
    query,
    requested_unit,
    desired_quantity
):
    candidates = []

    for url in _sq_site_urls(provider):
        score = _sq_score_text(url, query)

        if score > 0:
            score += _sq_desired_size_bonus(
                url,
                requested_unit,
                desired_quantity
            )
            candidates.append({
                "url": url,
                "score": score
            })

    base = provider["base"].rstrip("/")
    encoded = _sq_quote(query)

    for search_url in [
        f"{base}/productos/?q={encoded}",
        f"{base}/buscar?q={encoded}",
        f"{base}/search?q={encoded}",
        *[
            _sq_urljoin(base + "/", path.lstrip("/"))
            for path in provider.get("fallback_paths", [])
        ]
    ]:
        try:
            html = _sq_fetch(search_url, timeout=7)
        except Exception:
            continue

        for item in _sq_extract_links(
            html,
            search_url,
            provider,
            query
        ):
            item["score"] += _sq_desired_size_bonus(
                item["url"],
                requested_unit,
                desired_quantity
            )
            candidates.append(item)

    best_by_url = {}

    for item in candidates:
        current = best_by_url.get(item["url"])
        if current is None or item["score"] > current["score"]:
            best_by_url[item["url"]] = item

    result = list(best_by_url.values())
    result.sort(key=lambda item: item["score"], reverse=True)
    return result[:25]


def _sq_extract_balanced(text, start_index):
    if start_index < 0 or start_index >= len(text):
        return None

    opening = text[start_index]

    if opening not in "[{":
        return None

    closing = "]" if opening == "[" else "}"
    depth = 0
    in_string = False
    quote = ""
    escaped = False

    for index in range(start_index, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                in_string = False
            continue

        if char in {'"', "'"}:
            in_string = True
            quote = char
            continue

        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1

            if depth == 0:
                return text[start_index:index + 1]

    return None


def _sq_json_assignment(html, marker_pattern):
    match = _sq_re.search(
        marker_pattern,
        html or "",
        flags=_sq_re.IGNORECASE
    )

    if not match:
        return None

    index = match.end()

    while index < len(html) and html[index] not in "[{":
        index += 1

    raw = _sq_extract_balanced(html, index)

    if not raw:
        return None

    try:
        return _sq_json.loads(raw)
    except Exception:
        return None


def _sq_flat_text(value):
    if value is None:
        return ""

    if isinstance(value, (str, int, float)):
        return str(value)

    if isinstance(value, list):
        return " ".join(_sq_flat_text(item) for item in value)

    if isinstance(value, dict):
        return " ".join(
            _sq_flat_text(item)
            for item in value.values()
        )

    return ""


def _sq_variant_price(record):
    if not isinstance(record, dict):
        return None

    # Primero los precios ya formateados: evitan confundir centavos.
    for key in (
        "price_short",
        "price_long",
        "formatted_price",
        "price_formatted"
    ):
        if record.get(key) not in (None, ""):
            price = _sq_price_number(record.get(key))
            if price:
                return price

    for key in (
        "price",
        "price_number",
        "regular_price",
        "list_price",
        "amount"
    ):
        if record.get(key) not in (None, ""):
            price = _sq_price_number(record.get(key))
            if price:
                return price

    return None


def _sq_variants_from_tiendanube(html, requested_unit):
    data = _sq_json_assignment(
        html,
        r"LS\.variants\s*="
    )

    if not isinstance(data, list):
        return []

    result = []

    for record in data:
        if not isinstance(record, dict):
            continue

        size_text = _sq_flat_text(
            record.get("values")
            or record.get("options")
            or record.get("name")
            or record.get("variant")
        )

        size = _sq_find_size(size_text)
        price = _sq_variant_price(record)

        if not size or not price:
            continue

        requested = _sq_norm(requested_unit)

        if requested.startswith("ml") and size["unit"] != "ml":
            continue
        if requested.startswith("g") and size["unit"] != "g":
            continue

        result.append({
            "quantity": size["quantity"],
            "unit": size["unit"],
            "price": price,
            "source": "LS.variants"
        })

    return result


def _sq_price_fields(segment):
    result = []

    patterns = [
        r'(?i)["\'](?:price|precio|regular_price|list_price|amount|final_price)["\']\s*:\s*["\']?\$?\s*([0-9][0-9.,]*)',
        r'(?i)(?:data-price|data-precio)=["\']\$?\s*([0-9][0-9.,]*)["\']'
    ]

    for pattern in patterns:
        for match in _sq_re.finditer(pattern, segment or ""):
            price = _sq_price_number(match.group(1))
            if price:
                result.append(price)

    return result


def _sq_variants_from_embedded_html(html, requested_unit):
    # Empretienda suele incluir datos de opciones/variantes en scripts.
    scripts = _sq_re.findall(
        r"(?is)<script[^>]*>(.*?)</script>",
        html or ""
    )

    variants = []

    for script in scripts:
        for size_match in _sq_re.finditer(
            r"(?i)\b([0-9]+(?:[.,][0-9]+)?)\s*(cc|ml|mililitros?|l|litros?|lts?|g|grs?|gramos?|kg|kilos?)\b",
            script
        ):
            converted = _sq_convert_size(
                size_match.group(1),
                size_match.group(2)
            )

            if not converted:
                continue

            quantity, unit = converted
            requested = _sq_norm(requested_unit)

            if requested.startswith("ml") and unit != "ml":
                continue
            if requested.startswith("g") and unit != "g":
                continue

            # Intentamos quedarnos dentro del objeto JS/JSON de esa variante.
            before = script.rfind(
                "{",
                max(0, size_match.start() - 900),
                size_match.start()
            )

            after = script.find(
                "}",
                size_match.end(),
                min(len(script), size_match.end() + 900)
            )

            if before >= 0 and after > before:
                segment = script[before:after + 1]
            else:
                segment = script[
                    max(0, size_match.start() - 350):
                    min(len(script), size_match.end() + 350)
                ]

            prices = _sq_price_fields(segment)

            if not prices:
                continue

            # Un objeto de variante debería tener un precio principal.
            # Si aparecen varios, tomamos el primero y evitamos barrer toda la página.
            variants.append({
                "quantity": quantity,
                "unit": unit,
                "price": prices[0],
                "source": "embedded_variant"
            })

    # Deduplicación: misma presentación/precio.
    unique = []
    seen = set()

    for item in variants:
        key = (
            round(item["quantity"], 4),
            item["unit"],
            round(item["price"], 2)
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def _sq_choose_variant(
    variants,
    requested_unit,
    desired_quantity
):
    if not variants:
        return None

    requested = _sq_norm(requested_unit)
    compatible = []

    for item in variants:
        if requested.startswith("ml") and item["unit"] != "ml":
            continue
        if requested.startswith("g") and item["unit"] != "g":
            continue
        compatible.append(item)

    if not compatible:
        return None

    if desired_quantity and desired_quantity > 0:
        exact = [
            item for item in compatible
            if abs(item["quantity"] - desired_quantity) < 0.001
        ]

        if exact:
            return exact[0]

        return min(
            compatible,
            key=lambda item:
                abs(item["quantity"] - desired_quantity)
        )

    return compatible[0]


def _sq_main_price(html):
    # JSON-LD: si tiene precio exacto lo usamos.
    blocks = _sq_re.findall(
        r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html or ""
    )

    for block in blocks:
        try:
            data = _sq_json.loads(block.strip())
        except Exception:
            continue

        stack = [data]

        while stack:
            obj = stack.pop()

            if isinstance(obj, dict):
                if str(obj.get("@type", "")).lower() == "product":
                    offers = obj.get("offers")

                    if isinstance(offers, dict):
                        # NO usamos highPrice/lowPrice para variantes.
                        if offers.get("price") not in (None, ""):
                            price = _sq_price_number(offers.get("price"))
                            if price:
                                return price

                    if isinstance(offers, list):
                        for offer in offers:
                            if isinstance(offer, dict) and offer.get("price") not in (None, ""):
                                price = _sq_price_number(offer.get("price"))
                                if price:
                                    return price

                stack.extend(obj.values())

            elif isinstance(obj, list):
                stack.extend(obj)

    text = _sq_strip_html(html)

    match = _sq_re.search(
        r"\$\s*([0-9][0-9.\s]*(?:,[0-9]{1,2})?)",
        text
    )

    return _sq_price_number(match.group(1)) if match else None


def _sq_provider_quote(
    provider,
    query,
    requested_unit,
    desired_quantity
):
    try:
        candidates = _sq_candidate_urls(
            provider,
            query,
            requested_unit,
            desired_quantity
        )

        if not candidates:
            return {
                "provider": provider["name"],
                "status": "not_found",
                "message": "No encontré una ficha coincidente.",
                "store_url": provider["base"]
            }

        possible = []

        for candidate in candidates[:10]:
            try:
                html = _sq_fetch(candidate["url"], timeout=10)
            except Exception:
                continue

            title = _sq_extract_title(html)

            if not _sq_title_acceptable(title, query):
                continue

            score = _sq_score_text(title, query)
            score += _sq_desired_size_bonus(
                title,
                requested_unit,
                desired_quantity
            )

            variants = []

            if provider["kind"] == "tiendanube":
                variants = _sq_variants_from_tiendanube(
                    html,
                    requested_unit
                )
            elif provider["kind"] == "empretienda":
                variants = _sq_variants_from_embedded_html(
                    html,
                    requested_unit
                )

            chosen = _sq_choose_variant(
                variants,
                requested_unit,
                desired_quantity
            )

            if chosen:
                price = chosen["price"]
                quantity = chosen["quantity"]
                unit = chosen["unit"]
                exact = (
                    not desired_quantity
                    or desired_quantity <= 0
                    or abs(quantity - desired_quantity) < 0.001
                )

                row = {
                    "provider": provider["name"],
                    "status": "ok",
                    "product_name": title,
                    "product_url": candidate["url"],
                    "store_url": provider["base"],
                    "price": price,
                    "presentation_quantity": quantity,
                    "presentation_unit": unit,
                    "presentation_confidence":
                        "high" if exact else "medium",
                    "normalized_cost":
                        (price / quantity * 100)
                        if quantity > 0 else None,
                    "estimated_cost":
                        (price / quantity * desired_quantity)
                        if quantity > 0
                        and desired_quantity
                        and desired_quantity > 0
                        else None,
                    "score": score + (60 if exact else 20),
                    "message":
                        "" if exact
                        else "No encontré exactamente la cantidad pedida; se muestra la presentación más cercana."
                }
                possible.append(row)
                continue

            # Para productos que tienen una página separada por presentación,
            # el título contiene la cantidad exacta.
            title_size = _sq_find_size(title)
            main_price = _sq_main_price(html)

            if title_size and main_price:
                requested = _sq_norm(requested_unit)

                unit_ok = (
                    (requested.startswith("ml") and title_size["unit"] == "ml")
                    or
                    (requested.startswith("g") and title_size["unit"] == "g")
                    or
                    not requested
                )

                if unit_ok:
                    exact = (
                        not desired_quantity
                        or desired_quantity <= 0
                        or abs(
                            title_size["quantity"]
                            - desired_quantity
                        ) < 0.001
                    )

                    row = {
                        "provider": provider["name"],
                        "status": "ok",
                        "product_name": title,
                        "product_url": candidate["url"],
                        "store_url": provider["base"],
                        "price": main_price,
                        "presentation_quantity":
                            title_size["quantity"],
                        "presentation_unit":
                            title_size["unit"],
                        "presentation_confidence":
                            "high" if exact else "medium",
                        "normalized_cost":
                            main_price
                            / title_size["quantity"]
                            * 100,
                        "estimated_cost":
                            (
                                main_price
                                / title_size["quantity"]
                                * desired_quantity
                            )
                            if desired_quantity
                            and desired_quantity > 0
                            else None,
                        "score": score + (60 if exact else 10),
                        "message":
                            "" if exact
                            else "Se encontró otra presentación."
                    }
                    possible.append(row)
                    continue

            # Encontramos el producto pero no un precio ligado
            # de forma segura a una presentación.
            if main_price:
                possible.append({
                    "provider": provider["name"],
                    "status": "ok",
                    "product_name": title,
                    "product_url": candidate["url"],
                    "store_url": provider["base"],
                    "price": main_price,
                    "presentation_quantity": None,
                    "presentation_unit": "",
                    "presentation_confidence": "none",
                    "normalized_cost": None,
                    "estimated_cost": None,
                    "score": score - 30,
                    "message":
                        "Encontré el producto, pero no pude asociar con seguridad el precio a la presentación solicitada."
                })

        if not possible:
            return {
                "provider": provider["name"],
                "status": "not_found",
                "message":
                    "No encontré una coincidencia suficientemente segura.",
                "store_url": provider["base"]
            }

        possible.sort(
            key=lambda row: row["score"],
            reverse=True
        )

        best = possible[0]
        best.pop("score", None)
        return best

    except Exception as error:
        return {
            "provider": provider["name"],
            "status": "error",
            "message":
                "No se pudo consultar la tienda: "
                + str(error)[:180],
            "store_url": provider["base"]
        }


@app.get("/supplier-web-quotes")
def supplier_web_quotes(
    query: str,
    unit: str = "",
    quantity: float = 0
):
    material = str(query or "").strip()

    if len(material) < 2:
        return JSONResponse(
            status_code=400,
            content={"error": "Indicá una materia prima."}
        )

    desired_quantity = max(float(quantity or 0), 0)

    with _sq_ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(
                _sq_provider_quote,
                provider,
                material,
                unit,
                desired_quantity
            )
            for provider in _SQ_PROVIDERS
        ]

        results = [future.result() for future in futures]

    comparable = [
        row
        for row in results
        if row.get("status") == "ok"
        and row.get("normalized_cost") is not None
    ]

    comparable.sort(
        key=lambda row: row["normalized_cost"]
    )

    rank = {
        row["provider"]: index + 1
        for index, row in enumerate(comparable)
    }

    for row in results:
        row["rank"] = rank.get(row.get("provider"))

    return {
        "query": material,
        "unit": unit,
        "quantity": desired_quantity,
        "results": results,
        "price_notes": [
            "Precio web publicado, sin envío.",
            "El ranking solo usa precios ligados a una presentación identificada.",
            "Para tiendas con variantes se intenta leer la variante exacta, no el precio inicial de la página."
        ]
    }
