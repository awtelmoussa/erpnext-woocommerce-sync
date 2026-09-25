from erpnext_client import get_item, get_item_price, get_stock, get_items
from woocommerce_client import find_product_by_sku, wc_post, wc_put, get_or_create_category
from config import ERPNEXT_URL
from utils import logger
import threading

product_locks = {}
product_locks_lock = threading.Lock()

def get_product_lock(item_code):
    with product_locks_lock:
        if item_code not in product_locks:
            product_locks[item_code] = threading.Lock()
        return product_locks[item_code]


def build_product_payload(item_code):
    item = get_item(item_code)
    price = get_item_price(item_code)
    stock = get_stock(item_code)

    image_path = item.get("image")
    image_url = None

    if image_path:
        image_url = f"{ERPNEXT_URL}{image_path}"

    category_name = item.get("item_group")
    category = None
    if category_name:
        try:
            category = get_or_create_category(category_name)
        except Exception as e:
            logger.warning(
                f"Failed to resolve WooCommerce category '{category_name}' for item '{item_code}': {e}. "
                f"Proceeding without category."
            )

    if stock:
        available_stock = stock.get("actual_qty", 0) - stock.get("reserved_qty", 0)
    else:
        available_stock = item.get("opening_stock", 0)

    standard_rate = item.get("standard_rate")
    if standard_rate is None:
        standard_rate = 0

    product = {
        "sku": item["item_code"],
        "name": item["item_name"],
        "description": item.get("description") or "",
        "regular_price": str(
            price["price_list_rate"] if price else standard_rate
        ),
        "manage_stock": True,
        "stock_quantity": int(max(0, available_stock)),
        "type": "simple"
    }

    if category:
        product["categories"] = [
            {"id": category["id"]}
        ]

    if image_url:
        product["images"] = [
            {
                "src": image_url
            }
        ]

    return product


def sync_products(limit=10, start=0):
    items = get_items(limit=limit, start=start)

    logger.info(f"Found {len(items)} ERP items to sync")

    for item_row in items:
        item_code = item_row["name"]

        logger.info(f"Processing item: {item_code}")

        try:
            product = build_product_payload(item_code)
            logger.info(f"SKU: {product['sku']} | Name: {product['name']}")

            existing_product = find_product_by_sku(product["sku"])

            if existing_product:
                logger.info(f"Updating existing WooCommerce product: {existing_product['id']}")

                updated_product = wc_put(
                    f"/wp-json/wc/v3/products/{existing_product['id']}",
                    product
                )

                logger.info(f"Updated WooCommerce ID: {updated_product['id']}")

            else:
                logger.info("Creating product...")

                created_product = wc_post(
                    "/wp-json/wc/v3/products",
                    product
                )

                logger.info(f"Created WooCommerce ID: {created_product['id']}")
                find_product_by_sku.cache_clear()

        except Exception as error:
            logger.error(f"ERROR while processing item {item_code}: {error}")
            continue


def sync_one_product(item_code):
    lock = get_product_lock(item_code)
    with lock:
        logger.info(f"Processing one product sync: {item_code}")

        try:
            product = build_product_payload(item_code)

            logger.info(
                f"SKU: {product['sku']} | Name: {product['name']} | "
                f"Price: {product['regular_price']} | Stock: {product['stock_quantity']}"
            )

            existing_product = find_product_by_sku(product["sku"])

            if existing_product:
                logger.info(f"Updating existing WooCommerce product: {existing_product['id']}")

                updated_product = wc_put(
                    f"/wp-json/wc/v3/products/{existing_product['id']}",
                    product
                )

                logger.info(f"Updated WooCommerce ID: {updated_product['id']}")

            else:
                logger.info("Creating product...")

                created_product = wc_post(
                    "/wp-json/wc/v3/products",
                    product
                )

                logger.info(f"Created WooCommerce ID: {created_product['id']}")
                find_product_by_sku.cache_clear()

        except Exception as error:
            logger.error(f"ERROR while processing item {item_code}: {error}")