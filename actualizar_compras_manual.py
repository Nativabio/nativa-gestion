from pathlib import Path
from datetime import datetime
import re
import shutil
import sys

MAIN_FILE = Path("main.py")

if not MAIN_FILE.exists():
    print("ERROR: no encontré main.py.")
    print("Guardá este archivo dentro de la carpeta backend y ejecutalo nuevamente.")
    sys.exit(1)

source = MAIN_FILE.read_text(encoding="utf-8")

backup_name = (
    f"main.py.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
shutil.copy2(MAIN_FILE, backup_name)

if "import json" not in source:
    source = source.replace(
        "from uuid import uuid4",
        "from uuid import uuid4\nimport json",
        1
    )

if '"code": "5.3.01"' not in source:
    account_target = '''        {
            "code": "5.2.01",
            "name": "Gasto de Mano de Obra",
            "type": "GASTO",
            "category": "GASTO"
        }'''

    account_replacement = account_target + ''',

        {
            "code": "5.3.01",
            "name": "Materiales y gastos de producción",
            "type": "GASTO",
            "category": "GASTO"
        }'''

    if account_target in source:
        source = source.replace(
            account_target,
            account_replacement,
            1
        )
    else:
        print(
            "AVISO: no pude agregar la cuenta 5.3.01 al plan de cuentas."
        )

get_purchases_replacement = r'''@app.get("/purchases")
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


@app.post("/purchases")'''

get_pattern = re.compile(
    r'@app\.get\("/purchases"\)\n'
    r'def get_purchases\(.*?'
    r'\n\n@app\.post\("/purchases"\)',
    re.DOTALL
)

source, get_count = get_pattern.subn(
    get_purchases_replacement,
    source,
    count=1
)

if get_count != 1:
    print("ERROR: no pude actualizar el historial de compras.")
    print(f"Se creó una copia de seguridad: {backup_name}")
    sys.exit(1)

purchase_items_replacement = r'''@app.post("/purchase-items")
def create_purchase_items(
    data: dict,
    db: Session = Depends(get_db)
):

    purchase = db.query(Purchase).filter(
        Purchase.id == data["purchase_id"]
    ).first()

    if not purchase:

        return {
            "error": "Compra no encontrada"
        }

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

        if quantity <= 0 or price < 0:

            continue

        clean_items.append({
            "raw_material_id":
            item.get(
                "raw_material_id"
            ),

            "quantity":
            quantity,

            "price":
            price
        })

    material_base_total = sum(
        item["price"]
        for item in clean_items
    )

    material_total = 0

    for item in clean_items:

        material = db.query(RawMaterial).filter(
            RawMaterial.id
            ==
            item["raw_material_id"]
        ).first()

        if not material:

            continue

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

        purchase_item = PurchaseItem(

            purchase_id=purchase.id,

            raw_material_id=material.id,

            quantity=item["quantity"],

            price=final_price

        )

        db.add(purchase_item)

        material.stock = (
            float(material.stock or 0)
            +
            item["quantity"]
        )

        material.cost = (
            final_price
            /
            item["quantity"]
        )

        material_total += final_price

    clean_extra_items = []

    extra_total = 0

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

        if (
            not name
            or
            quantity <= 0
            or
            price < 0
        ):

            continue

        clean_extra_items.append({

            "name":
            name,

            "category":
            category,

            "quantity":
            quantity,

            "price":
            price

        })

        extra_total += price

    unallocated_shipping = 0

    if material_base_total <= 0:

        unallocated_shipping = (
            shipping_cost
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

        return {
            "error":
            "La compra no tiene importes válidos"
        }

    metadata = {

        "shipping_cost":
        shipping_cost,

        "extra_items":
        clean_extra_items,

        "notes":
        ""

    }

    purchase.notes = (
        "__NATIVA_PURCHASE_META__"
        +
        json.dumps(
            metadata,
            ensure_ascii=False
        )
    )

    purchase.total = total

    if purchase.payment_method == "Banco":

        payment_code = "1.1.02"
        payment_name = "Banco"

    elif purchase.payment_method == "Mercado Pago":

        payment_code = "1.1.03"
        payment_name = "Mercado Pago"

    elif purchase.payment_method in [
        "Proveedores",
        "Cuenta corriente"
    ]:

        payment_code = "2.1.01"
        payment_name = "Proveedores"

    else:

        payment_code = "1.1.01"
        payment_name = "Caja"

    group_id = str(
        uuid4()
    )

    if material_total > 0:

        db.add(
            JournalEntry(

                date=purchase.date,

                concept=(
                    f"Compra {purchase.number}"
                ),

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

                concept=(
                    f"Compra {purchase.number}"
                ),

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

            concept=(
                f"Compra {purchase.number}"
            ),

            account_code=payment_code,

            account_name=payment_name,

            debit=0,

            credit=total,

            entry_group=group_id,

            origin="COMPRA",

            origin_id=purchase.id

        )
    )

    db.commit()

    return {

        "message":
        "Compra completa guardada y contabilizada",

        "total":
        total

    }


# ================= COMPRAS ITEMS ================='''

items_pattern = re.compile(
    r'@app\.post\("/purchase-items"\)\n'
    r'def create_purchase_items\(.*?'
    r'\n\s*# ================= COMPRAS ITEMS =================',
    re.DOTALL
)

source, items_count = items_pattern.subn(
    purchase_items_replacement,
    source,
    count=1
)

if items_count != 1:
    print("ERROR: no pude actualizar el guardado de compras.")
    print(f"Se creó una copia de seguridad: {backup_name}")
    sys.exit(1)

try:
    compile(
        source,
        str(MAIN_FILE),
        "exec"
    )
except SyntaxError as error:
    print("ERROR: la modificación produjo un problema de sintaxis.")
    print(error)
    print(f"Tu archivo original quedó guardado como: {backup_name}")
    sys.exit(1)

MAIN_FILE.write_text(
    source,
    encoding="utf-8"
)

print("LISTO: main.py fue actualizado correctamente.")
print(f"Copia de seguridad creada: {backup_name}")
