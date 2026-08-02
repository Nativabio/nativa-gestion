from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date
from pydantic import BaseModel
from sqlalchemy.orm import relationship

from database import Base


# ================= PRODUCTOS =================

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String)

    price = Column(Float, default=0)

    stock = Column(Float, default=0)

class ProductCreate(BaseModel):

    name: str

    price: float = 0

    stock: float = 0    

# ================= PROVEEDORES =================

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String)

    business_name = Column(String)

    tax_id = Column(String)

    phone = Column(String)

    email = Column(String)

    address = Column(String)

    city = Column(String)

    province = Column(String)

    contact = Column(String)

    payment_terms = Column(String)

    notes = Column(String)

# ================= VENTAS =================

class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)

    number = Column(String)

    client = Column(String)

    date = Column(String)

    payment_method = Column(String)

    total = Column(Float, default=0)

    shipping_cost = Column(Float, default=0)

    amount_paid = Column(Float, default=0)

    balance = Column(Float, default=0)

    payment_status = Column(String, default="PAGADA")

    items = relationship(
        "SaleItem",
        back_populates="sale"
    )

    payments = relationship(
        "SalePayment",
        back_populates="sale",
        cascade="all, delete-orphan"
    )
    returned_containers = relationship(
        "SaleReturnedContainer",
        back_populates="sale",
        cascade="all, delete-orphan"
    )


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)

    sale_id = Column(Integer, ForeignKey("sales.id"))

    product_id = Column(Integer, ForeignKey("products.id"))

    quantity = Column(Float)

    price = Column(Float)

    subtotal = Column(Float)

    cost_total = Column(Float, default=0)

    sale = relationship(
        "Sale",
        back_populates="items"
    )


class SalePayment(Base):
    __tablename__ = "sale_payments"

    id = Column(Integer, primary_key=True, index=True)

    number = Column(String, unique=True, index=True)

    sale_id = Column(
        Integer,
        ForeignKey("sales.id", ondelete="CASCADE")
    )

    date = Column(String)

    payment_method = Column(String)

    amount = Column(Float, default=0)

    notes = Column(String, default="")

    sale = relationship(
        "Sale",
        back_populates="payments"
    )


class SaleReturnedContainer(Base):
    __tablename__ = "sale_returned_containers"

    id = Column(Integer, primary_key=True, index=True)

    sale_id = Column(
        Integer,
        ForeignKey("sales.id", ondelete="CASCADE")
    )

    raw_material_id = Column(
        Integer,
        ForeignKey("raw_materials.id")
    )

    quantity = Column(Float, default=0)

    sale = relationship(
        "Sale",
        back_populates="returned_containers"
    )

    raw_material = relationship("RawMaterial")


class SaleLotAllocation(Base):
    __tablename__ = "sale_lot_allocations"

    id = Column(Integer, primary_key=True, index=True)

    sale_item_id = Column(
        Integer,
        ForeignKey("sale_items.id")
    )

    lot_id = Column(
        Integer,
        ForeignKey("lots.id")
    )

    quantity = Column(Float, default=0)

    unit_cost = Column(Float, default=0)

    subtotal_cost = Column(Float, default=0)


# ================= BAJAS DE STOCK =================

class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)

    number = Column(String, unique=True, index=True)

    date = Column(String)

    reason = Column(String)

    movement_type = Column(String, default="OUT")

    notes = Column(String, default="")

    total_cost = Column(Float, default=0)

    items = relationship(
        "StockMovementItem",
        back_populates="movement",
        cascade="all, delete-orphan"
    )


class StockMovementItem(Base):
    __tablename__ = "stock_movement_items"

    id = Column(Integer, primary_key=True, index=True)

    stock_movement_id = Column(
        Integer,
        ForeignKey("stock_movements.id", ondelete="CASCADE")
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id")
    )

    quantity = Column(Float, default=0)

    cost_total = Column(Float, default=0)

    movement = relationship(
        "StockMovement",
        back_populates="items"
    )

    product = relationship("Product")

    allocations = relationship(
        "StockMovementLotAllocation",
        back_populates="movement_item",
        cascade="all, delete-orphan"
    )


class StockMovementLotAllocation(Base):
    __tablename__ = "stock_movement_lot_allocations"

    id = Column(Integer, primary_key=True, index=True)

    stock_movement_item_id = Column(
        Integer,
        ForeignKey("stock_movement_items.id", ondelete="CASCADE")
    )

    lot_id = Column(
        Integer,
        ForeignKey("lots.id")
    )

    quantity = Column(Float, default=0)

    unit_cost = Column(Float, default=0)

    subtotal_cost = Column(Float, default=0)

    movement_item = relationship(
        "StockMovementItem",
        back_populates="allocations"
    )


# ================= COMPRAS =================

class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)

    number = Column(String, unique=True)

    supplier = Column(String)

    invoice_number = Column(String)

    payment_method = Column(String)

    date = Column(String)

    notes = Column(String)

    total = Column(Float, default=0)



class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True, index=True)

    purchase_id = Column(Integer, ForeignKey("purchases.id"))

    raw_material_id = Column(Integer, ForeignKey("raw_materials.id"))

    quantity = Column(Float)

    price = Column(Float)

    raw_material = relationship("RawMaterial")


# ================= CONTABILIDAD =================

class Accounting(Base):
    __tablename__ = "accounting"

    id = Column(Integer, primary_key=True, index=True)

    type = Column(String)

    description = Column(String)

    amount = Column(Float)

# ================= PLAN DE CUENTAS =================

class Account(Base):

    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String, unique=True)

    name = Column(String)

    type = Column(String)

    category = Column(String)

    active = Column(Integer, default=1)

class JournalEntry(Base):

    __tablename__ = "journal_entries"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    date = Column(String)

    concept = Column(String)

    account_code = Column(String)

    account_name = Column(String)

    debit = Column(Float, default=0)

    credit = Column(Float, default=0)

    entry_group = Column(String, index=True)

    origin = Column(String, default="MANUAL")

    origin_id = Column(Integer)

# ================= LIBRO DIARIO =================

class Journal(Base):

    __tablename__ = "journal"

    id = Column(Integer, primary_key=True, index=True)

    date = Column(String)

    concept = Column(String)

    origin = Column(String)

    origin_id = Column(Integer)

    details = relationship(
        "JournalDetail",
        back_populates="journal"
    )


class JournalDetail(Base):

    __tablename__ = "journal_detail"

    id = Column(Integer, primary_key=True, index=True)

    journal_id = Column(
        Integer,
        ForeignKey("journal.id")
    )

    account_id = Column(
        Integer,
        ForeignKey("accounts.id")
    )

    debit = Column(Float, default=0)

    credit = Column(Float, default=0)

    journal = relationship(
        "Journal",
        back_populates="details"
    )

    account = relationship("Account")    

# ================= FORMULAS =================

class Formula(Base):
    __tablename__ = "formulas"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String)

    output_product_id = Column(Integer)

    output_raw_material_id = Column(
        Integer,
        ForeignKey("raw_materials.id")
    )

    output_type = Column(String, default="PRODUCT")

    batch_size = Column(Float, default=1)

    labor_hours = Column(Float, default=0)

    units_produced = Column(Float, default=1)

    margin_percent = Column(Float, default=40)

    notes = Column(String, default="")



class FormulaItem(Base):
    __tablename__ = "formula_items"

    id = Column(Integer, primary_key=True, index=True)

    formula_id = Column(
        Integer,
        ForeignKey("formulas.id")
    )

    raw_material_id = Column(
        Integer,
        ForeignKey("raw_materials.id")
    )

    quantity = Column(Float, default=0)

    raw_material = relationship("RawMaterial")



# ================= MATERIAS PRIMAS =================

class RawMaterial(Base):
    __tablename__ = "raw_materials"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String, unique=True, index=True, nullable=True)

    name = Column(String)

    is_intermediate = Column(Integer, default=0)

    category = Column(String)

    unit = Column(String)

    stock = Column(Float, default=0)

    minimum_stock = Column(Float, default=0)

    cost = Column(Float, default=0)

    supplier = Column(String)

    location = Column(String)

class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)

    labor_hour_cost = Column(Float, default=10000)

    currency = Column(String, default="$")


# ================= LOTES =================

class Lot(Base):
    __tablename__ = "lots"

    id = Column(Integer, primary_key=True, index=True)

    lot_number = Column(String, unique=True)

    formula_id = Column(Integer, ForeignKey("formulas.id"))

    formula = relationship("Formula")

    output_type = Column(String, default="PRODUCT")

    output_raw_material_id = Column(
        Integer,
        ForeignKey("raw_materials.id")
    )

    origin = Column(String, default="PRODUCTION")

    production_date = Column(Date)

    expiration_date = Column(Date)

    units_produced = Column(Float)

    remaining_units = Column(Float)

    real_labor_hours = Column(Float)

    material_cost = Column(Float, default=0)

    labor_cost = Column(Float, default=0)

    total_cost = Column(Float, default=0)

    unit_cost = Column(Float, default=0)

    inventory_unit_cost = Column(Float, default=0)

    notes = Column(String)

    status = Column(String, default="Disponible")

# ================= TRAZABILIDAD DE INTERMEDIOS =================

class LotMaterialSourceAllocation(Base):
    __tablename__ = "lot_material_source_allocations"

    id = Column(Integer, primary_key=True, index=True)

    consumer_lot_id = Column(
        Integer,
        ForeignKey("lots.id", ondelete="CASCADE")
    )

    raw_material_id = Column(
        Integer,
        ForeignKey("raw_materials.id")
    )

    source_lot_id = Column(
        Integer,
        ForeignKey("lots.id")
    )

    quantity = Column(Float, default=0)

    unit_cost = Column(Float, default=0)

    subtotal_cost = Column(Float, default=0)
