import time
from datetime import datetime, timedelta
from product_sync import sync_products
from erpnext_client import (
    get_or_create_customer,
    create_sales_order,
    submit_sales_order,
    update_sales_order_status_note,
    add_sales_order_comment
)
from processed_orders import (
    is_order_processed,
    mark_order_processed,
    get_processed_order,
    check_and_lock_order,
    unlock_order,
    get_metadata,
    set_metadata
)
from order_sync import get_latest_orders, get_order, build_order_payload, get_orders_since
from utils import logger


ORDER_SYNC_SECONDS = 60
PRODUCT_SYNC_SECONDS = 15 * 60


def process_order_sync(order):
    order_payload = build_order_payload(order)
    woo_order_id = order_payload["woo_order_id"]
    woo_status = order_payload["status"]

    success, processed_order = check_and_lock_order(woo_order_id, woo_status)
    if not success:
        if processed_order and processed_order.get("status") == "processing":
            logger.info(f"Woo order {woo_order_id} is currently being processed. Skipping.")
            return {"status": "processing", "woo_order_id": woo_order_id}
        else:
            logger.info(f"Skipping already processed Woo order: {woo_order_id}")
            return {"status": "skipped", "woo_order_id": woo_order_id}

    old_status = processed_order.get("status") if processed_order else None
    sales_order_name = processed_order.get("sales_order") if processed_order else "PENDING_CREATION"

    try:
        if processed_order and sales_order_name != "PENDING_CREATION":
            if old_status != woo_status:
                logger.info(
                    f"Woo order {woo_order_id} status changed: "
                    f"{old_status} -> {woo_status}"
                )

                add_sales_order_comment(
                    sales_order_name,
                    f"WooCommerce order status changed from {old_status} to {woo_status}"
                )

                if woo_status == "cancelled":
                    add_sales_order_comment(
                        sales_order_name,
                        "WooCommerce order was cancelled, but ERP Sales Order could not be auto-cancelled. Please cancel/release stock reservation manually."
                    )

                mark_order_processed(
                    woo_order_id,
                    sales_order_name,
                    woo_status
                )

                return {
                    "status": "updated",
                    "woo_order_id": woo_order_id,
                    "old_status": old_status,
                    "new_status": woo_status,
                    "sales_order": sales_order_name
                }

            logger.info(f"Skipping already processed Woo order: {woo_order_id}")
            return {
                "status": "skipped",
                "woo_order_id": woo_order_id
            }

        customer = get_or_create_customer(order_payload)

        sales_order = create_sales_order(
            order_payload,
            customer
        )

        submit_sales_order(
            sales_order["name"]
        )

        mark_order_processed(
            woo_order_id,
            sales_order["name"],
            woo_status
        )

        logger.info(f"Sales Order created/synced: {sales_order['name']}")

        return {
            "status": "created",
            "woo_order_id": woo_order_id,
            "sales_order": sales_order["name"]
        }

    except Exception as error:
        logger.error(f"ERROR processing order {woo_order_id}: {error}")
        unlock_order(woo_order_id, old_status, sales_order_name)
        raise error


def sync_orders(limit=20):
    # Default to 3 days ago if never synced before
    default_after = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
    last_sync = get_metadata("last_order_sync_time", default_after)

    logger.info(f"Syncing WooCommerce orders modified since: {last_sync}")

    page = 1
    total_processed = 0
    max_modified_time = last_sync
    per_page = limit if limit else 50

    while True:
        orders = get_orders_since(last_sync, page=page, limit=per_page)
        if not orders:
            break

        logger.info(f"Fetched {len(orders)} orders on page {page}")

        for order in orders:
            try:
                res = process_order_sync(order)
                if res.get("status") in ("created", "updated"):
                    total_processed += 1
            except Exception as e:
                logger.error(f"Failed to process order {order.get('id')}: {e}")

            modified_time = order.get("date_modified")
            if modified_time and modified_time > max_modified_time:
                max_modified_time = modified_time

        if len(orders) < per_page:
            break
        page += 1

    if max_modified_time > last_sync:
        set_metadata("last_order_sync_time", max_modified_time)
        logger.info(f"Advanced order sync checkpoint to: {max_modified_time}")

    logger.info(f"Sync orders completed. Processed {total_processed} new/updated orders.")


def sync_products_light():
    sync_products(limit=50, start=0)


def run_full_sync():
    logger.info("Starting full sync...")

    logger.info("Syncing products...")
    sync_products_light()

    logger.info("Syncing orders...")
    sync_orders(limit=20)

    logger.info("Full sync finished.")


def run_forever():
    logger.info("Starting automatic sync service...")

    last_product_sync = 0

    while True:
        now = time.time()

        try:
            logger.info("Checking WooCommerce orders...")
            sync_orders(limit=20)

            if now - last_product_sync >= PRODUCT_SYNC_SECONDS:
                logger.info("Syncing ERP products to WooCommerce...")
                sync_products_light()
                last_product_sync = now

        except Exception as error:
            logger.error(f"ERROR in sync loop: {error}")

        logger.info(f"Waiting {ORDER_SYNC_SECONDS} seconds...")
        time.sleep(ORDER_SYNC_SECONDS)


def sync_one_order_by_id(order_id):
    try:
        order = get_order(order_id)
        return process_order_sync(order)
    except Exception as e:
        logger.error(f"Failed to sync order {order_id}: {e}")
        return {"status": "error", "message": str(e)}
