from pydantic import BaseModel
from typing import Optional


# ================= PRODUCTOS =================

class ProductCreate(BaseModel):
    name: str
    price: float
    stock: float


# ================= MATERIAS PRIMAS =================

class RawMaterialCreate(BaseModel):
    code: Optional[str] = ""
    name: str
    category: str = ""
    unit: str
    stock: float = 0
    minimum_stock: float = 0
    cost: float = 0
    supplier: str = ""
    location: str = ""
    is_intermediate: int = 0


# ================= FORMULAS =================

class FormulaCreate(BaseModel):
    name: str
    output_product_id: Optional[int] = None
    output_raw_material_id: Optional[int] = None
    output_type: str = "PRODUCT"
    batch_size: float
    labor_hours: float = 0
    units_produced: float = 1
    notes: str = ""


class FormulaItemCreate(BaseModel):
    formula_id: int
    raw_material_id: int
    quantity: float

    # ================= LOTES =================

class LotCreate(BaseModel):

    formula_id: int

    production_date: str

    expiration_date: str

    units_produced: float

    real_labor_hours: float

    notes: str = ""

    # ================= PROVEEDORES =================

class SupplierCreate(BaseModel):
    name: str

    business_name: str = ""

    tax_id: str = ""

    phone: str = ""

    email: str = ""

    address: str = ""

    city: str = ""

    province: str = ""

    contact: str = ""

    payment_terms: str = ""

    notes: str = ""