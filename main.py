from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import text

from datetime import datetime
import base64
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4

from database import SessionLocal, Base, engine

from typing import Optional

from models import (
    Product,
    Sale,
    SaleItem,
    SaleLotAllocation,
    StockMovement,
    StockMovementItem,
    StockMovementLotAllocation,
    Purchase,
    PurchaseItem,
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
    JournalDetail
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
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS payment_method VARCHAR"
        )
    )

    conn.execute(
        text(
            "ALTER TABLE formulas ADD COLUMN IF NOT EXISTS margin_percent FLOAT DEFAULT 40"
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
                ('PURCHASE', 0)
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
            "code": "1.1.03",
            "name": "Mercado Pago",
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
            "code": "5.2.01",
            "name": "Gasto de Mano de Obra",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.3.01",
            "name": "Materiales y gastos de producción",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.4.01",
            "name": "Diferencias de stock",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.4.02",
            "name": "Testeo y control de calidad",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.4.03",
            "name": "Consumo personal de productos",
            "type": "GASTO",
            "category": "GASTO"
        },

        {
            "code": "5.4.04",
            "name": "Regalos y obsequios",
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



create_default_accounts()


def infer_journal_origin(
    concept
):

    normalized = str(
        concept or ""
    ).strip().lower()

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


def get_inventory_unit_cost(
    lot
):

    units = float(
        lot.units_produced or 0
    )

    if units <= 0:

        return 0

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

@app.get("/products")
def get_products(
    db: Session = Depends(get_db)
):

    products = (
        db.query(Product)
        .order_by(Product.name.asc())
        .all()
    )

    result = []

    for product in products:

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

        result.append({
            "id": product.id,
            "name": product.name,
            "price": float(product.price or 0),
            "stock": float(product.stock or 0),
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
            "error":"Producto no encontrado"
        }


    db.delete(product)

    db.commit()


    return {
        "message":"Producto eliminado"
    }    



@app.post("/products")
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db)
):

    item = Product(

        name=product.name,

        price=product.price,

        stock=product.stock

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

    product.price = data["price"]

    db.commit()

    db.refresh(product)

    return product    

# ================= VENTAS =================

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

    if payment_method == "Banco":

        return (
            "1.1.02",
            "Banco"
        )

    if payment_method == "Mercado Pago":

        return (
            "1.1.03",
            "Mercado Pago"
        )

    return (
        "1.1.01",
        "Caja"
    )


def restore_sale_details(
    db,
    sale
):

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
            "CMV"
        ])
    ).delete(
        synchronize_session=False
    )

    db.query(JournalEntry).filter(
        JournalEntry.origin_id.is_(None),
        JournalEntry.concept.in_([
            f"Venta {sale.number}",
            f"Costo de venta {sale.number}"
        ])
    ).delete(
        synchronize_session=False
    )

    sale.total = 0

    db.flush()


def apply_sale_items(
    db,
    sale,
    items_data
):

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
    total_cost_of_sale = 0
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

        sale_item.cost_total = item_cost

        product.stock = (
            float(product.stock or 0)
            -
            quantity
        )

        sale.total += subtotal
        total_cost_of_sale += item_cost

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

    if total_cost_of_sale > 0:

        registrar_asiento(
            db=db,
            fecha=sale.date,
            concepto=f"Costo de venta {sale.number}",
            debe_codigo="5.1.01",
            debe_nombre="Costo de Ventas",
            haber_codigo="1.2.02",
            haber_nombre="Productos Terminados",
            importe=total_cost_of_sale,
            origin="CMV",
            origin_id=sale.id
        )

    return (
        total_cost_of_sale,
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

        total_cost, zero_cost_lots = (
            apply_sale_items(
                db,
                sale,
                data.get("items", [])
            )
        )

        db.commit()

        response = {
            "mensaje":
            "Venta guardada correctamente",
            "costo_venta":
            round(total_cost, 2)
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

        sale.payment_method = str(
            data.get(
                "payment_method",
                "Caja"
            )
            or
            "Caja"
        ).strip()

        total_cost, zero_cost_lots = (
            apply_sale_items(
                db,
                sale,
                data.get("items", [])
            )
        )

        db.commit()

        response = {
            "mensaje":
            f"Venta {sale.number} modificada correctamente",
            "costo_venta":
            round(total_cost, 2)
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

    products = db.query(Product).all()

    product_name_by_id = {

        product.id:
        product.name

        for product in products

    }

    items_by_sale = {}

    for item in sale_items:

        items_by_sale.setdefault(
            item.sale_id,
            []
        ).append({

            "id":
            item.id,

            "product_id":
            item.product_id,

            "name":
            product_name_by_id.get(
                item.product_id,
                "Producto sin nombre"
            ),

            "quantity":
            float(
                item.quantity or 0
            ),

            "price":
            float(
                item.price or 0
            ),

            "subtotal":
            float(
                item.subtotal or 0
            )

        })

    return [

        {

            "id":
            sale.id,

            "number":
            sale.number,

            "client":
            sale.client,

            "date":
            sale.date,

            "payment_method":
            sale.payment_method,

            "total":
            float(
                sale.total or 0
            ),

            "items":
            items_by_sale.get(
                sale.id,
                []
            )

        }

        for sale in sales

    ]


def reverse_and_delete_sale(
    db,
    sale
):

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
        "5.4.01",

        "account_name":
        "Diferencias de stock"
    },

    "LOT_TEST": {
        "label":
        "Testeo de lote",

        "account_code":
        "5.4.02",

        "account_name":
        "Testeo y control de calidad"
    },

    "PERSONAL_USE": {
        "label":
        "Consumo personal",

        "account_code":
        "5.4.03",

        "account_name":
        "Consumo personal de productos"
    },

    "GIFT": {
        "label":
        "Regalo u obsequio",

        "account_code":
        "5.4.04",

        "account_name":
        "Regalos y obsequios"
    }

}


@app.post("/stock-movements")
def create_stock_movement(
    data: dict,
    db: Session = Depends(get_db)
):

    date = str(
        data.get(
            "date",
            ""
        )
    ).strip()

    reason = str(
        data.get(
            "reason",
            ""
        )
    ).strip().upper()

    notes = str(
        data.get(
            "notes",
            ""
        )
    ).strip()

    items_data = data.get(
        "items",
        []
    )

    if not date:

        return {
            "error":
            "La fecha es obligatoria"
        }

    reason_data = (
        STOCK_MOVEMENT_REASONS.get(
            reason
        )
    )

    if not reason_data:

        return {
            "error":
            "El motivo de la baja no es válido"
        }

    if not isinstance(
        items_data,
        list
    ) or not items_data:

        return {
            "error":
            "Agregá al menos un producto"
        }

    quantities_by_product = {}

    for item in items_data:

        try:

            product_id = int(
                item.get(
                    "product_id"
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

        except (
            TypeError,
            ValueError
        ):

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
            quantities_by_product.get(
                product_id,
                0
            )
            +
            quantity
        )

    products_by_id = {}

    # ==========================
    # VALIDAR STOCK GENERAL Y FIFO
    # ==========================

    for product_id, required_quantity in (
        quantities_by_product.items()
    ):

        product = db.query(Product).filter(
            Product.id == product_id
        ).first()

        if not product:

            return {
                "error":
                "Uno de los productos no existe"
            }

        products_by_id[product_id] = product

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
        notes=notes,
        total_cost=0
    )

    try:

        db.add(movement)
        db.flush()

        movement.number = (
            f"BS{movement.id:04d}"
        )

        total_cost = 0
        zero_cost_lots = []

        # ==========================
        # DESCONTAR PRODUCTOS POR FIFO
        # ==========================

        for product_id, quantity in (
            quantities_by_product.items()
        ):

            product = products_by_id[
                product_id
            ]

            movement_item = StockMovementItem(
                stock_movement_id=movement.id,
                product_id=product.id,
                quantity=quantity,
                cost_total=0
            )

            db.add(movement_item)
            db.flush()

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

                unit_cost = (
                    get_inventory_unit_cost(
                        lot
                    )
                )

                subtotal_cost = (
                    quantity_used
                    *
                    unit_cost
                )

                db.add(
                    StockMovementLotAllocation(
                        stock_movement_item_id=
                        movement_item.id,
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

                quantity_to_allocate -= (
                    quantity_used
                )

                if quantity_to_allocate <= 0.000001:

                    break

            if quantity_to_allocate > 0.000001:

                raise ValueError(
                    f"No fue posible asignar todos los lotes "
                    f"de {product.name}"
                )

            movement_item.cost_total = (
                item_cost
            )

            product.stock = (
                float(product.stock or 0)
                -
                quantity
            )

            total_cost += item_cost

        movement.total_cost = total_cost

        # Un único asiento por registración, aunque incluya varios productos.
        if total_cost > 0:

            registrar_asiento(
                db=db,
                fecha=date,
                concepto=(
                    f"Baja de stock {movement.number} - "
                    f"{reason_data['label']}"
                ),
                debe_codigo=
                reason_data["account_code"],
                debe_nombre=
                reason_data["account_name"],
                haber_codigo="1.2.02",
                haber_nombre="Productos Terminados",
                importe=total_cost,
                origin="BAJA_STOCK",
                origin_id=movement.id
            )

        db.commit()
        db.refresh(movement)

        response = {
            "id":
            movement.id,

            "number":
            movement.number,

            "message":
            "Baja de stock guardada correctamente",

            "total_cost":
            round(total_cost, 2)
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
            f"No se pudo guardar la baja de stock: {error}"
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

    movement_items = (
        db.query(StockMovementItem).all()
    )

    products = db.query(Product).all()

    product_name_by_id = {
        product.id:
        product.name
        for product in products
    }

    items_by_movement = {}

    for item in movement_items:

        items_by_movement.setdefault(
            item.stock_movement_id,
            []
        ).append({
            "id":
            item.id,

            "product_id":
            item.product_id,

            "name":
            product_name_by_id.get(
                item.product_id,
                "Producto sin nombre"
            ),

            "quantity":
            float(item.quantity or 0),

            "cost_total":
            float(item.cost_total or 0)
        })

    return [
        {
            "id":
            movement.id,

            "number":
            movement.number,

            "date":
            movement.date,

            "reason":
            movement.reason,

            "reason_label":
            STOCK_MOVEMENT_REASONS.get(
                movement.reason,
                {}
            ).get(
                "label",
                movement.reason
            ),

            "notes":
            movement.notes or "",

            "total_cost":
            float(movement.total_cost or 0),

            "items":
            items_by_movement.get(
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
            "Baja de stock no encontrada"
        }

    try:

        movement_items = (
            db.query(StockMovementItem)
            .filter(
                StockMovementItem.stock_movement_id
                ==
                movement.id
            )
            .all()
        )

        for item in movement_items:

            allocations = (
                db.query(StockMovementLotAllocation)
                .filter(
                    StockMovementLotAllocation.stock_movement_item_id
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
            JournalEntry.origin == "BAJA_STOCK",
            JournalEntry.origin_id == movement.id
        ).delete(
            synchronize_session=False
        )

        db.query(JournalEntry).filter(
            JournalEntry.origin_id.is_(None),
            JournalEntry.concept.like(
                f"Baja de stock {movement.number}%"
            )
        ).delete(
            synchronize_session=False
        )

        db.delete(movement)
        db.commit()

        return {
            "message":
            f"Baja de stock {movement.number} eliminada correctamente"
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo eliminar la baja de stock: {error}"
        }

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

    purchase_items = (
        db.query(PurchaseItem).all()
    )

    raw_materials = (
        db.query(RawMaterial).all()
    )

    suppliers = db.query(Supplier).all()

    material_by_id = {

        material.id:
        material

        for material in raw_materials

    }

    supplier_name_by_id = {

        str(supplier.id):
        supplier.name

        for supplier in suppliers

    }

    supplier_name_by_name = {

        str(supplier.name).strip().lower():
        supplier.name

        for supplier in suppliers

        if supplier.name

    }

    items_by_purchase = {}

    for item in purchase_items:

        material = material_by_id.get(
            item.raw_material_id
        )

        items_by_purchase.setdefault(
            item.purchase_id,
            []
        ).append({

            "id":
            item.id,

            "raw_material_id":
            item.raw_material_id,

            "name":
            (
                material.name
                if material
                else
                "Materia prima sin nombre"
            ),

            "unit":
            (
                material.unit
                if material
                else
                ""
            ),

            "quantity":
            float(
                item.quantity or 0
            ),

            "price":
            float(
                item.price or 0
            )

        })

    result = []

    metadata_prefix = (
        "__NATIVA_PURCHASE_META__"
    )

    for purchase in purchases:

        supplier_value = str(
            purchase.supplier or ""
        ).strip()

        supplier_name = (
            supplier_name_by_id.get(
                supplier_value
            )
        )

        if not supplier_name:

            supplier_name = (
                supplier_name_by_name.get(
                    supplier_value.lower()
                )
            )

        if not supplier_name:

            supplier_name = (
                supplier_value
                or
                "Sin proveedor"
            )

        raw_notes = str(
            purchase.notes or ""
        )

        metadata = {}

        visible_notes = raw_notes

        if raw_notes.startswith(
            metadata_prefix
        ):

            try:

                metadata = json.loads(
                    raw_notes[
                        len(metadata_prefix):
                    ]
                )

                visible_notes = str(
                    metadata.get(
                        "notes",
                        ""
                    )
                )

            except Exception:

                metadata = {}
                visible_notes = raw_notes

        extra_items = metadata.get(
            "extra_items",
            []
        )

        if not isinstance(
            extra_items,
            list
        ):

            extra_items = []

        result.append({

            "id":
            purchase.id,

            "number":
            purchase.number,

            "supplier":
            supplier_name,

            "supplier_reference":
            supplier_value,

            "invoice_number":
            purchase.invoice_number,

            "payment_method":
            purchase.payment_method,

            "date":
            purchase.date,

            "notes":
            visible_notes,

            "shipping_cost":
            float(
                metadata.get(
                    "shipping_cost",
                    0
                )
                or
                0
            ),

            "extra_items":
            extra_items,

            "total":
            float(
                purchase.total or 0
            ),

            "items":
            items_by_purchase.get(
                purchase.id,
                []
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
            "1.1.03",
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


def clean_purchase_payload(
    data
):

    items = data.get(
        "items",
        []
    )

    extra_items = data.get(
        "extra_items",
        []
    )

    shipping_cost = max(
        float(
            data.get(
                "shipping_cost",
                0
            )
            or
            0
        ),
        0
    )

    clean_items = []

    for item in items:

        raw_material_id = int(
            item.get("raw_material_id")
        )

        quantity = float(
            item.get(
                "quantity",
                0
            )
            or
            0
        )

        price = float(
            item.get(
                "price",
                0
            )
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
            "raw_material_id":
            raw_material_id,
            "quantity":
            quantity,
            "price":
            price
        })

    clean_extra_items = []

    for item in extra_items:

        name = str(
            item.get(
                "name",
                ""
            )
            or
            ""
        ).strip()

        category = str(
            item.get(
                "category",
                "Otro"
            )
            or
            "Otro"
        ).strip()

        quantity = float(
            item.get(
                "quantity",
                0
            )
            or
            0
        )

        price = float(
            item.get(
                "price",
                0
            )
            or
            0
        )

        if not name:

            continue

        if quantity <= 0:

            raise ValueError(
                "Las cantidades de otros gastos deben ser mayores a cero"
            )

        if price < 0:

            raise ValueError(
                "Los importes no pueden ser negativos"
            )

        clean_extra_items.append({
            "name": name,
            "category": category,
            "quantity": quantity,
            "price": price
        })

    if not clean_items and not clean_extra_items and shipping_cost <= 0:

        raise ValueError(
            "La compra no tiene importes válidos"
        )

    return (
        clean_items,
        clean_extra_items,
        shipping_cost
    )


def purchase_quantities_by_material(
    db,
    purchase_id
):

    result = {}

    for item in db.query(PurchaseItem).filter(
        PurchaseItem.purchase_id == purchase_id
    ).all():

        result[item.raw_material_id] = (
            result.get(
                item.raw_material_id,
                0
            )
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

    quantities = {}

    for item in purchase_items:

        quantities[item.raw_material_id] = (
            quantities.get(
                item.raw_material_id,
                0
            )
            +
            float(item.quantity or 0)
        )

    materials_by_id = {}

    if adjust_stock:

        for material_id, quantity in quantities.items():

            material = (
                db.query(RawMaterial)
                .filter(
                    RawMaterial.id == material_id
                )
                .with_for_update()
                .first()
            )

            if not material:

                continue

            if (
                float(material.stock or 0)
                +
                0.000001
                <
                quantity
            ):

                raise ValueError(
                    (
                        f"No se puede revertir la compra porque "
                        f"ya se consumió parte del stock de "
                        f"{material.name}. Stock actual: "
                        f"{float(material.stock or 0)}"
                    )
                )

            materials_by_id[material_id] = material

        for material_id, quantity in quantities.items():

            material = materials_by_id.get(
                material_id
            )

            if material:

                material.stock = (
                    float(material.stock or 0)
                    -
                    quantity
                )

    for item in purchase_items:

        db.delete(item)

    db.query(JournalEntry).filter(
        JournalEntry.origin == "COMPRA",
        JournalEntry.origin_id == purchase.id
    ).delete(
        synchronize_session=False
    )

    db.query(JournalEntry).filter(
        JournalEntry.origin_id.is_(None),
        JournalEntry.concept == (
            f"Compra {purchase.number}"
        )
    ).delete(
        synchronize_session=False
    )

    purchase.total = 0

    db.flush()

    return set(quantities.keys())


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
                PurchaseItem.raw_material_id == material_id
            )
            .order_by(
                Purchase.date.desc(),
                PurchaseItem.id.desc()
            )
            .first()
        )

        if (
            latest_item
            and
            float(latest_item.quantity or 0) > 0
        ):

            material.cost = (
                float(latest_item.price or 0)
                /
                float(latest_item.quantity or 0)
            )

        else:

            material.cost = 0


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

    materials_by_id = {}

    for item in clean_items:

        material = (
            db.query(RawMaterial)
            .filter(
                RawMaterial.id
                ==
                item["raw_material_id"]
            )
            .with_for_update()
            .first()
        )

        if not material:

            raise ValueError(
                "Una de las materias primas no existe"
            )

        materials_by_id[material.id] = material

    material_base_total = sum(
        item["price"]
        for item in clean_items
    )

    material_total = 0
    affected_material_ids = set()

    for item in clean_items:

        material = materials_by_id[
            item["raw_material_id"]
        ]

        allocated_shipping = 0

        if material_base_total > 0:

            allocated_shipping = (
                shipping_cost
                *
                item["price"]
                /
                material_base_total
            )

        final_price = (
            item["price"]
            +
            allocated_shipping
        )

        db.add(
            PurchaseItem(
                purchase_id=purchase.id,
                raw_material_id=material.id,
                quantity=item["quantity"],
                price=final_price
            )
        )

        if adjust_stock:

            material.stock = (
                float(material.stock or 0)
                +
                item["quantity"]
            )

        material_total += final_price
        affected_material_ids.add(material.id)

    extra_total = sum(
        item["price"]
        for item in clean_extra_items
    )

    unallocated_shipping = (
        shipping_cost
        if material_base_total <= 0
        else
        0
    )

    expense_total = (
        extra_total
        +
        unallocated_shipping
    )

    total = (
        material_total
        +
        expense_total
    )

    if total <= 0:

        raise ValueError(
            "La compra no tiene importes válidos"
        )

    metadata = {
        "shipping_cost":
        shipping_cost,
        "extra_items":
        clean_extra_items,
        "notes":
        str(
            data.get(
                "notes",
                ""
            )
            or
            ""
        )
    }

    purchase.notes = (
        PURCHASE_METADATA_PREFIX
        +
        json.dumps(
            metadata,
            ensure_ascii=False
        )
    )

    purchase.total = total

    payment_code, payment_name = (
        purchase_payment_account(
            purchase.payment_method
        )
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

    if expense_total > 0:

        db.add(
            JournalEntry(
                date=purchase.date,
                concept=f"Compra {purchase.number}",
                account_code="5.3.01",
                account_name=(
                    "Materiales y gastos de producción"
                ),
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

    recalculate_raw_material_costs(
        db,
        affected_material_ids
    )

    return (
        total,
        affected_material_ids
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

        total, _ = apply_purchase_contents(
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

        return {
            "error":
            "Compra no encontrada"
        }

    try:

        cleaned_payload = clean_purchase_payload(
            data
        )

        clean_items = cleaned_payload[0]

        old_quantities = (
            purchase_quantities_by_material(
                db,
                purchase.id
            )
        )

        new_quantities = {}

        for item in clean_items:

            material_id = item["raw_material_id"]

            new_quantities[material_id] = (
                new_quantities.get(
                    material_id,
                    0
                )
                +
                item["quantity"]
            )

        all_material_ids = (
            set(old_quantities)
            |
            set(new_quantities)
        )

        materials_by_id = {}

        for material_id in all_material_ids:

            material = (
                db.query(RawMaterial)
                .filter(
                    RawMaterial.id == material_id
                )
                .with_for_update()
                .first()
            )

            if not material:

                raise ValueError(
                    "Una de las materias primas no existe"
                )

            delta = (
                new_quantities.get(
                    material_id,
                    0
                )
                -
                old_quantities.get(
                    material_id,
                    0
                )
            )

            if (
                float(material.stock or 0)
                +
                delta
                <
                -0.000001
            ):

                raise ValueError(
                    (
                        f"No se puede reducir esa cantidad de "
                        f"{material.name} porque parte del stock "
                        f"ya fue consumido. Stock actual: "
                        f"{float(material.stock or 0)}"
                    )
                )

            materials_by_id[material_id] = (
                material,
                delta
            )

        old_material_ids = remove_purchase_contents(
            db,
            purchase,
            adjust_stock=False
        )

        for material, delta in materials_by_id.values():

            material.stock = (
                float(material.stock or 0)
                +
                delta
            )

        purchase.supplier = str(
            data.get(
                "supplier",
                purchase.supplier
            )
        ).strip()

        purchase.invoice_number = str(
            data.get(
                "invoice_number",
                ""
            )
            or
            ""
        ).strip()

        purchase.payment_method = str(
            data.get(
                "payment_method",
                "Caja"
            )
            or
            "Caja"
        ).strip()

        purchase.date = str(
            data.get(
                "date",
                purchase.date
            )
        ).strip()

        total, new_material_ids = (
            apply_purchase_contents(
                db,
                purchase,
                data,
                adjust_stock=False,
                cleaned_payload=cleaned_payload
            )
        )

        recalculate_raw_material_costs(
            db,
            old_material_ids
            |
            new_material_ids
        )

        db.commit()

        return {
            "message":
            f"Compra {purchase.number} modificada correctamente",
            "total":
            total
        }

    except Exception as error:

        db.rollback()

        return {
            "error":
            f"No se pudo modificar la compra: {error}"
        }


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


    subtotal = product.price * qty


    item = PurchaseItem(
        purchase_id=purchase.id,
        product_id=product.id,
        quantity=qty,
        price=product.price
    )


    product.stock += qty

    purchase.total += subtotal


    db.add(item)

    db.commit()


    return {
        "mensaje": "compra actualizada"
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
        return {"error": "No existe"}

    item.code = material.code
    item.name = material.name
    item.category = material.category
    item.unit = material.unit
    item.stock = material.stock
    item.minimum_stock = material.minimum_stock
    item.cost = material.cost
    item.supplier = material.supplier
    item.location = material.location

    db.commit()
    db.refresh(item)

    return item

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

    try:

        affected_material_ids = (
            remove_purchase_contents(
                db,
                purchase
            )
        )

        purchase_number = purchase.number

        db.delete(purchase)
        db.flush()

        recalculate_raw_material_costs(
            db,
            affected_material_ids
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

    return db.query(Account).all()
    
@app.post("/accounts")
def create_account(
    data: dict,
    db: Session = Depends(get_db)
):

    account = Account(

        code=data["code"],

        name=data["name"],

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
                account_code="5.2.01",
                account_name="Gasto de Mano de Obra",
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
                    origin_id

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

            product_name = (
                product_name_by_id.get(
                    formula.output_product_id
                )
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

    return (
        db.query(Formula)
        .order_by(
            Formula.name.asc()
        )
        .all()
    )


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


@app.post("/formulas")
def create_formula(
    data: dict,
    db: Session = Depends(get_db)
):

    try:

        item = Formula(
            name=str(data.get("name", "")).strip(),
            output_product_id=int(data.get("output_product_id")),
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

        item.name = name
        item.output_product_id = int(
            data.get(
                "output_product_id",
                item.output_product_id
            )
        )
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
        item.margin_percent = (
            validated_formula_margin(
                data.get(
                    "margin_percent",
                    item.margin_percent
                )
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
        return {"error": "Fórmula no encontrada"}

    db.query(FormulaItem).filter(
        FormulaItem.formula_id == formula_id
    ).delete()

    db.delete(item)
    db.commit()

    return {"message": "Fórmula eliminada"}

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
            "raw_material_id":
            row["raw_material_id"],

            "name":
            row["name"]
            or
            "Materia prima eliminada",

            "unit":
            row["unit"]
            or
            "",

            "quantity":
            float(row["quantity"] or 0),

            "unit_cost":
            float(row["unit_cost"] or 0),

            "subtotal_cost":
            float(row["subtotal_cost"] or 0),

            "source":
            row["source"]
            or
            "REAL"
        })

    allocation_lot_ids = {
        row[0]
        for row in (
            db.query(
                SaleLotAllocation.lot_id
            )
            .distinct()
            .all()
        )
    }

    result = []

    for lot in lots:

        formula = formula_by_id.get(
            lot.formula_id
        )

        product_id = (
            formula.output_product_id
            if formula
            else
            None
        )

        materials = materials_by_lot.get(
            lot.id,
            []
        )

        has_estimated_materials = any(
            material["source"]
            ==
            "FORMULA_ESTIMATE"
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

        has_sales = (
            lot.id
            in
            allocation_lot_ids
        )

        can_delete = (
            not has_sales
            and
            abs(
                remaining_units
                -
                units_produced
            )
            <
            0.000001
        )

        result.append({
            "id":
            lot.id,

            "lot_number":
            lot.lot_number,

            "formula_id":
            lot.formula_id,

            "formula_name":
            formula.name
            if formula
            else
            "Fórmula eliminada",

            "product_id":
            product_id,

            "product_name":
            product_name_by_id.get(
                product_id,
                "Producto sin identificar"
            ),

            "production_date":
            str(lot.production_date or "")[:10],

            "expiration_date":
            str(lot.expiration_date or "")[:10],

            "units_produced":
            units_produced,

            "remaining_units":
            remaining_units,

            "real_labor_hours":
            float(lot.real_labor_hours or 0),

            "material_cost":
            float(lot.material_cost or 0),

            "labor_cost":
            float(lot.labor_cost or 0),

            "total_cost":
            float(lot.total_cost or 0),

            "unit_cost":
            float(lot.unit_cost or 0),

            "notes":
            lot.notes or "",

            "status":
            lot.status
            or
            (
                "Disponible"
                if remaining_units > 0
                else
                "Agotado"
            ),

            "materials":
            materials,

            "material_history_source":
            (
                "FORMULA_ESTIMATE"
                if has_estimated_materials
                else
                "REAL"
            ),

            "has_sales":
            has_sales,

            "can_delete":
            can_delete,

            "delete_block_reason":
            (
                "El lote ya fue utilizado en una venta."
                if has_sales
                else
                (
                    "El lote ya tiene unidades consumidas o ajustadas."
                    if not can_delete
                    else
                    ""
                )
            )
        })

    return result


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

    allocations = (
        db.query(SaleLotAllocation)
        .filter(
            SaleLotAllocation.lot_id
            ==
            lot.id
        )
        .count()
    )

    units_produced = float(
        lot.units_produced or 0
    )

    remaining_units = float(
        lot.remaining_units
        if lot.remaining_units is not None
        else units_produced
    )

    if (
        allocations > 0
        or
        abs(
            remaining_units
            -
            units_produced
        )
        >
        0.000001
    ):

        return {
            "error":
            (
                "No se puede eliminar este lote porque "
                "ya fue utilizado total o parcialmente en ventas."
            )
        }

    formula = db.query(Formula).filter(
        Formula.id == lot.formula_id
    ).first()

    product = None

    if formula:

        product = db.query(Product).filter(
            Product.id
            ==
            formula.output_product_id
        ).first()

    if not product:

        return {
            "error":
            "No se encontró el producto terminado asociado al lote"
        }

    if (
        float(product.stock or 0)
        +
        0.000001
        <
        units_produced
    ):

        return {
            "error":
            (
                "No se puede eliminar el lote porque el stock actual "
                "del producto terminado es menor que las unidades del lote."
            )
        }

    material_rows = db.execute(
        text(
            """
            SELECT
                raw_material_id,
                quantity,
                source
            FROM lot_materials
            WHERE lot_id = :lot_id
            """
        ),
        {
            "lot_id":
            lot.id
        }
    ).mappings().all()

    if not material_rows:

        return {
            "error":
            (
                "Este lote no tiene guardado el detalle de materias primas "
                "y no puede eliminarse de forma segura."
            )
        }

    used_estimated_history = any(
        row["source"]
        ==
        "FORMULA_ESTIMATE"
        for row in material_rows
    )

    try:

        for row in material_rows:

            raw = db.query(RawMaterial).filter(
                RawMaterial.id
                ==
                row["raw_material_id"]
            ).first()

            if raw:

                raw.stock = (
                    float(raw.stock or 0)
                    +
                    float(row["quantity"] or 0)
                )

        product.stock = (
            float(product.stock or 0)
            -
            units_produced
        )

        if product.stock < 0.000001:

            product.stock = max(
                float(product.stock or 0),
                0
            )

        db.query(JournalEntry).filter(
            JournalEntry.origin
            ==
            "PRODUCCION",
            JournalEntry.origin_id
            ==
            lot.id
        ).delete(
            synchronize_session=False
        )

        db.query(JournalEntry).filter(
            JournalEntry.origin_id.is_(None),
            JournalEntry.concept
            ==
            f"Producción lote {lot.lot_number}"
        ).delete(
            synchronize_session=False
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

        db.delete(lot)

        db.commit()

        return {
            "message":
            f"Lote {lot.lot_number} eliminado correctamente",

            "materials_restored":
            True,

            "used_estimated_history":
            used_estimated_history,

            "warning":
            (
                "Las materias primas se repusieron según la fórmula actual "
                "porque este lote es anterior al historial detallado."
                if used_estimated_history
                else
                ""
            )
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

    units_produced = float(
        lot["units_produced"]
    )

    real_labor_hours = float(
        lot.get(
            "real_labor_hours",
            0
        )
    )

    if units_produced <= 0:

        return {
            "error":
            "Las unidades producidas deben ser mayores a cero"
        }

    material_cost = 0

    materials_to_discount = []

    # ==========================
    # VALIDAR Y VALUAR MATERIAS PRIMAS
    # ==========================

    for material_data in lot.get(
        "materials",
        []
    ):

        raw = db.query(RawMaterial).filter(
            RawMaterial.id
            ==
            material_data["raw_material_id"]
        ).first()

        if not raw:

            return {
                "error":
                "Una de las materias primas no existe"
            }

        quantity_used = float(
            material_data["real_quantity"]
        )

        if quantity_used <= 0:

            return {
                "error":
                f"La cantidad usada de {raw.name} debe ser mayor a cero"
            }

        if (
            float(raw.stock or 0)
            +
            0.000001
            <
            quantity_used
        ):

            return {
                "error":
                (
                    f"Stock insuficiente de {raw.name}. "
                    f"Disponible: {raw.stock}"
                )
            }

        unit_material_cost = float(
            raw.cost or 0
        )

        material_cost += (
            quantity_used
            *
            unit_material_cost
        )

        materials_to_discount.append(
            (
                raw,
                quantity_used,
                unit_material_cost
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

    full_total_cost = (
        material_cost
        +
        labor_cost
    )

    full_unit_cost = (
        full_total_cost
        /
        units_produced
    )

    inventory_unit_cost = (
        material_cost
        /
        units_produced
    )

    formula = db.query(Formula).filter(
        Formula.id == lot["formula_id"]
    ).first()

    if not formula:

        return {
            "error":
            "Fórmula no encontrada"
        }

    product = db.query(Product).filter(
        Product.id == formula.output_product_id
    ).first()

    if not product:

        return {
            "error":
            "La fórmula no tiene un producto terminado válido"
        }

    try:

        lot_number = (
            take_next_document_number(
                db,
                "LOT"
            )
        )

        item = Lot(

            lot_number=lot_number,

            formula_id=lot["formula_id"],

            production_date=lot["production_date"],

            units_produced=units_produced,

            remaining_units=units_produced,

            real_labor_hours=real_labor_hours,

            material_cost=material_cost,

            labor_cost=labor_cost,

            total_cost=full_total_cost,

            unit_cost=full_unit_cost,

            inventory_unit_cost=inventory_unit_cost,

            notes=lot.get(
                "notes",
                ""
            )

        )

        db.add(item)

        db.flush()

        # ==========================
        # DESCONTAR MATERIAS PRIMAS
        # ==========================

        for (
            raw,
            quantity_used,
            unit_material_cost
        ) in materials_to_discount:

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
                    item.id,

                    "raw_material_id":
                    raw.id,

                    "quantity":
                    quantity_used,

                    "unit_cost":
                    unit_material_cost,

                    "subtotal_cost":
                    quantity_used
                    *
                    unit_material_cost
                }
            )

        # ==========================
        # AUMENTAR PRODUCTO TERMINADO
        # ==========================

        product.stock = (
            float(product.stock or 0)
            +
            units_produced
        )

        # ==========================
        # ASIENTO AUTOMÁTICO DE PRODUCCIÓN
        # ==========================

        registrar_asiento_produccion(

            db=db,

            fecha=lot["production_date"],

            concepto=(
                f"Producción lote {lot_number}"
            ),

            costo_materiales=material_cost,

            costo_mano_obra=labor_cost,

            origin_id=item.id

        )

        db.commit()

        db.refresh(item)

        return {

            "id": item.id,

            "lot_number": item.lot_number,

            "material_cost":
            round(material_cost, 2),

            "labor_cost":
            round(labor_cost, 2),

            "total_cost":
            round(full_total_cost, 2),

            "unit_cost":
            round(full_unit_cost, 2),

            "inventory_unit_cost":
            round(inventory_unit_cost, 2),

            "message":
            "Lote guardado y contabilizado correctamente"

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

    return (
        db.query(RawMaterial)
        .order_by(
            RawMaterial.name.asc()
        )
        .all()
    )


@app.post("/raw-materials")
def create_raw_material(
    material: RawMaterialCreate,
    db: Session = Depends(get_db)
):

    item = RawMaterial(
        code=material.code,
        name=material.name,
        category=material.category,
        unit=material.unit,
        stock=material.stock,
        minimum_stock=material.minimum_stock,
        cost=material.cost,
        supplier=material.supplier,
        location=material.location
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return item


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
        return {"error": "Materia prima no encontrada"}

    item.code = material.code
    item.name = material.name
    item.category = material.category
    item.unit = material.unit
    item.stock = material.stock
    item.minimum_stock = material.minimum_stock
    item.cost = material.cost
    item.supplier = material.supplier
    item.location = material.location

    db.commit()
    db.refresh(item)

    return item


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