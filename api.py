"""
api.py
The bridge between the JS frontend and the Python/SQLite backend.
Every method here is exposed to the browser window as window.pywebview.api.<method>
"""

import db


class Api:

    # ---- Scan / search ----

    def scan(self, code):
        code = (code or "").strip()
        if not code:
            return {"found": False}

        if code.isdigit() and len(code) == 15:
            result = db.lookup_by_imei(code)
            if result:
                if result["status"] == "sold":
                    return {"found": True, "already_sold": True, "product": result}
                return {"found": True, "type": "imei", "product": result}
            return {"found": False, "type": "imei", "code": code}

        result = db.lookup_by_sku(code)
        if result:
            return {"found": True, "type": "sku", "product": result}
        return {"found": False, "type": "sku", "code": code}

    def search_products(self, query):
        return db.search_products(query)

    def get_available_imeis(self, product_id):
        return db.get_available_imeis(product_id)

    # ---- Checkout ----

    def checkout(self, cart_items, payment_method):
        return db.record_sale(cart_items, payment_method)

    # ---- Inventory management ----

    def add_product(self, sku, name, category, price, cost, track_by, qty, reorder_level):
        return db.add_product(sku, name, category, float(price), float(cost),
                               track_by, int(qty or 0), int(reorder_level or 5))

    def add_imei_units(self, product_id, imei_text):
        imei_list = [x.strip() for x in (imei_text or "").splitlines() if x.strip()]
        return db.add_imei_units(int(product_id), imei_list)

    def restock_qty(self, product_id, amount):
        return db.restock_qty(int(product_id), int(amount))

    def get_all_products(self):
        return db.get_all_products()

    # ---- Reporting ----

    def get_low_stock(self):
        return db.get_low_stock()

    def get_sales_history(self, limit=50):
        return db.get_sales_history(limit)
