import requests
import time
from datetime import datetime, timedelta
from config import ERPNEXT_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET
from utils import sanitize_text, logger
import json
from functools import lru_cache

DEBUG = False

# Shared session for HTTP connection pooling (keep-alive)
session = requests.Session()
session.headers.update({
    "Authorization": f"token {ERPNEXT_API_KEY}:{ERPNEXT_API_SECRET}",
    "Accept": "application/json"
})


def erp_request(method, path, **kwargs):
    url = f"{ERPNEXT_URL}{path}"
    for attempt in range(3):
        try:
            response = session.request(method, url, **kwargs)
            
            if DEBUG:
                print(f"ERPNext {method} status: {response.status_code}")
                if response.status_code != 200:
                    print(response.text)
                    
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise e
            logger.warning(f"ERPNext request failed: {e}. Retrying in 2 seconds...")
            time.sleep(2)


def erp_get(path, params=None):
    return erp_request("GET", path, params=params)


def erp_post(path, payload):
    return erp_request("POST", path, json=payload)

# -------------------------
# ERP Items
# -------------------------

def get_items(limit=10, start=0):
    return erp_get(
        "/api/resource/Item",
        params={
            "fields": '["name","item_code","item_name","item_group","disabled","is_sales_item"]',
            "filters": '[["disabled","=",0],["is_sales_item","=",1]]',
            "limit_start": start,
            "limit_page_length": limit
        }
    )["data"]


def get_item(item_code):
    return erp_get(f"/api/resource/Item/{item_code}")["data"]


def get_item_price(item_code):
    data = erp_get(
        "/api/resource/Item Price",
        params={
            "filters": f'[["item_code","=","{item_code}"]]',
            "fields": '["name","item_code","price_list","price_list_rate","currency"]',
            "limit_page_length": 1
        }
    )["data"]

    return data[0] if data else None


def get_stock(item_code):
    data = erp_get(
        "/api/resource/Bin",
        params={
            "filters": f'[["item_code","=","{item_code}"]]',
            "fields": '["item_code","warehouse","actual_qty","projected_qty","reserved_qty"]',
            "limit_page_length": 1
        }
    )["data"]

    return data[0] if data else None


# -------------------------
# ERP Defaults
# -------------------------

@lru_cache(maxsize=1)
def get_default_company():
    companies = erp_get(
        "/api/resource/Company",
        params={
            "fields": '["name","default_currency"]',
            "limit_page_length": 1
        }
    )["data"]

    if not companies:
        raise Exception("No ERPNext company found")

    return companies[0]


@lru_cache(maxsize=10)
def get_default_warehouse(company_name):
    warehouses = erp_get(
        "/api/resource/Warehouse",
        params={
            "fields": '["name","company","is_group"]',
            "filters": f'[["company","=","{company_name}"],["is_group","=",0],["name","like","Stores%"]]',
            "limit_page_length": 1
        }
    )["data"]

    if not warehouses:
        raise Exception(f"No warehouse found for company: {company_name}")

    return warehouses[0]


@lru_cache(maxsize=1)
def get_default_selling_price_list():
    price_lists = erp_get(
        "/api/resource/Price List",
        params={
            "fields": '["name","selling"]',
            "filters": '[["selling","=",1]]',
            "limit_page_length": 1
        }
    )["data"]

    if not price_lists:
        return {"name": "Standard Selling"}

    return price_lists[0]


# -------------------------
# ERP Customers
# -------------------------

def find_customer_by_email(email):
    if not email:
        return None

    data = erp_get(
        "/api/resource/Customer",
        params={
            "filters": f'[["email_id","=","{email}"]]',
            "fields": '["name","customer_name","email_id","mobile_no"]',
            "limit_page_length": 1
        }
    )["data"]

    return data[0] if data else None


def find_customer_by_phone(phone):
    if not phone:
        return None

    data = erp_get(
        "/api/resource/Customer",
        params={
            "filters": f'[["mobile_no","=","{phone}"]]',
            "fields": '["name","customer_name","email_id","mobile_no"]',
            "limit_page_length": 1
        }
    )["data"]

    return data[0] if data else None


def create_customer(customer_name, email=None, phone=None):
    payload = {
        "customer_name": sanitize_text(customer_name),
        "customer_type": "Individual",
        "customer_group": "Individual",
        "territory": "All Territories",
        "email_id": sanitize_text(email).lower(),
        "mobile_no": sanitize_text(phone)
    }

    response = erp_post("/api/resource/Customer", payload)

    return response["data"]


def get_or_create_customer(order_payload):
    email = order_payload.get("email")
    phone = order_payload.get("phone")
    customer_name = order_payload.get("customer_name")

    existing_customer = find_customer_by_email(email)

    if not existing_customer:
        existing_customer = find_customer_by_phone(phone)

    if existing_customer:
        print("ERP customer already exists:", existing_customer["name"])
        return existing_customer

    print("Creating ERP customer:", customer_name)
    return create_customer(customer_name, email, phone)


# -------------------------
# ERP Sales Orders
# -------------------------

def create_sales_order(order_payload, customer):
    company = get_default_company()
    warehouse = get_default_warehouse(company["name"])
    price_list = get_default_selling_price_list()
    shipping_address = create_customer_address(order_payload, customer)

    today = datetime.now().strftime("%Y-%m-%d")
    delivery_date = (datetime.now() + timedelta(days=4)).strftime("%Y-%m-%d")

    items = []

    for item in order_payload["items"]:
        items.append({
            "item_code": item["sku"],
            "delivery_date": delivery_date,
            "qty": item["qty"],
            "rate": item["rate"],
            "warehouse": warehouse["name"],
            "reserve_stock": 1
        })

    payload = {
        "company": company["name"],
        "customer": customer["name"],
        "order_type": "Sales",
        "transaction_date": today,
        "delivery_date": delivery_date,
        "currency": company["default_currency"],
        "selling_price_list": price_list["name"],
        "reserve_stock": 1,

        "customer_address": shipping_address["name"],
        "shipping_address_name": shipping_address["name"],

        "po_no": f"WooCommerce Order #{order_payload['woo_order_id']}",
        "notes": (
            f"Created automatically from WooCommerce\n"
            f"Woo Order ID: {order_payload['woo_order_id']}\n"
            f"Customer Email: {order_payload.get('email')}\n"
            f"Customer Phone: {order_payload.get('phone')}\n"
            f"Delivery Address: {order_payload.get('address_1')} "
            f"{order_payload.get('address_2')}, "
            f"{order_payload.get('city')}, "
            f"{order_payload.get('country')}"
        ),

        "items": items
    }

    response = erp_post("/api/resource/Sales Order", payload)

    return response["data"]

def update_sales_order_status_note(sales_order_name, woo_status):
    payload = {
        "notes": f"WooCommerce order status updated to: {woo_status}"
    }
    return erp_request("PUT", f"/api/resource/Sales Order/{sales_order_name}", json=payload)["data"]

def add_sales_order_comment(sales_order_name, message):
    payload = {
        "comment_type": "Comment",
        "reference_doctype": "Sales Order",
        "reference_name": sales_order_name,
        "content": message
    }

    response = erp_post("/api/resource/Comment", payload)

    return response["data"]

def submit_sales_order(sales_order_name):
    sales_order = erp_get(
        f"/api/resource/Sales Order/{sales_order_name}"
    )["data"]

    payload = {
        "doc": json.dumps(sales_order)
    }

    erp_request("POST", "/api/method/frappe.client.submit", json=payload)
    print(f"Sales Order submitted: {sales_order_name}")

def cancel_sales_order(sales_order_name):
    sales_order = erp_get(
        f"/api/resource/Sales Order/{sales_order_name}"
    )["data"]

    payload = {
        "doc": json.dumps(sales_order)
    }

    erp_request("POST", "/api/method/frappe.client.cancel", json=payload)
    print(f"Sales Order cancelled: {sales_order_name}")    


def create_customer_address(order_payload, customer):
    payload = {
        "address_title": customer["name"],
        "address_type": "Shipping",
        "address_line1": order_payload.get("address_1") or "-",
        "address_line2": order_payload.get("address_2") or "",
        "city": order_payload.get("city") or "-",
        "country": normalize_country(order_payload.get("country")),
        "phone": order_payload.get("phone") or "",
        "email_id": order_payload.get("email") or "",
        "links": [
            {
                "link_doctype": "Customer",
                "link_name": customer["name"]
            }
        ]
    }

    response = erp_post("/api/resource/Address", payload)

    return response["data"]


def normalize_country(country):
    countries = {
        "SY": "Syria",
        "LB": "Lebanon",
        "AE": "United Arab Emirates",
        "SA": "Saudi Arabia",
        "QA": "Qatar",
        "KW": "Kuwait",
        "BH": "Bahrain",
        "OM": "Oman",
        "JO": "Jordan",
        "IQ": "Iraq",
        "TR": "Turkey",
        "EG": "Egypt",
        "US": "United States",
        "GB": "United Kingdom",
        "FR": "France",
        "DE": "Germany",
        "LV": "Latvia"
    }

    return countries.get(country, country or "Syria")