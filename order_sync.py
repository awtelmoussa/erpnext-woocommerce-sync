from woocommerce_client import wc_get
import json
from datetime import datetime, timedelta
from utils import sanitize_text

def get_latest_orders(limit=5):
    today = datetime.now()
    three_days_ago = today - timedelta(days=3)
    three_days_from_now = today + timedelta(days=3)

    after = three_days_ago.strftime("%Y-%m-%dT00:00:00")
    before = three_days_from_now.strftime("%Y-%m-%dT00:00:00")

    return wc_get(
        "/wp-json/wc/v3/orders",
        params={
            "per_page": limit,
            "after": after,
            "before": before,
            "status": "any"
        }
    )

def get_orders_since(after_timestamp, page=1, limit=50):
    return wc_get(
        "/wp-json/wc/v3/orders",
        params={
            "per_page": limit,
            "page": page,
            "after": after_timestamp,
            "orderby": "date",
            "order": "asc",
            "status": "any"
        }
    )

def get_order(order_id):
    return wc_get(
        f"/wp-json/wc/v3/orders/{order_id}"
    )


def get_delivery_address(order):
    billing = order.get("billing", {})
    shipping = order.get("shipping", {})

    if shipping.get("address_1"):
        return shipping

    return billing


def print_order_summary(order):
    print("--------------------------------")
    print("Order ID:", order["id"])
    print("Status:", order["status"])
    print("Total:", order["total"])
    print("Currency:", order["currency"])
    print("Payment Method:", order.get("payment_method_title"))

    billing = order.get("billing", {})
    delivery = get_delivery_address(order)

    print("\nCustomer:")
    print("Name:", billing.get("first_name"), billing.get("last_name"))
    print("Email:", billing.get("email"))
    print("Phone:", billing.get("phone"))

    print("\nDelivery Address:")
    print(delivery.get("address_1"))
    print(delivery.get("address_2"))
    print(delivery.get("city"))
    print(delivery.get("country"))

    print("\nItems:")
    for item in order.get("line_items", []):
        print(
            item.get("quantity"),
            "x",
            item.get("name"),
            "| SKU:",
            item.get("sku"),
            "| Total:",
            item.get("total")
        )


def build_order_payload(order):
    billing = order.get("billing", {})
    delivery = get_delivery_address(order)

    items = []

    for item in order.get("line_items", []):
        items.append({
            "sku": sanitize_text(item.get("sku")),
            "item_name": sanitize_text(item.get("name")),
            "qty": item.get("quantity"),
            "rate": item.get("price")
        })

    return {
        "woo_order_id": order["id"],
        "status": sanitize_text(order["status"]),
        "customer_name": sanitize_text(
            f"{billing.get('first_name')} {billing.get('last_name')}"
        ),
        "email": sanitize_text(billing.get("email")).lower(),
        "phone": sanitize_text(billing.get("phone")),
        "address_1": sanitize_text(delivery.get("address_1")),
        "address_2": sanitize_text(delivery.get("address_2")),
        "city": sanitize_text(delivery.get("city")),
        "country": sanitize_text(delivery.get("country")),
        "total": order["total"],
        "items": items
    }


def test_read_latest_orders():
    orders = get_latest_orders(limit=5)

    print(f"Found {len(orders)} WooCommerce orders")

    for order in orders:
        print_order_summary(order)


def test_order_payloads():
    orders = get_latest_orders(limit=5)

    print(f"Found {len(orders)} WooCommerce orders")

    for order in orders:
        payload = build_order_payload(order)
        print(json.dumps(payload, indent=4))