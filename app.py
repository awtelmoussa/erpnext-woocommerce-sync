import threading
from fastapi import FastAPI, Request, BackgroundTasks
from sync_runner import run_full_sync, run_forever, sync_one_order_by_id
from product_sync import sync_one_product
from utils import logger

app = FastAPI(title="ERPNext WooCommerce Sync")


@app.get("/health")
def health():
    return {
        "status": "running",
        "service": "ERPNext WooCommerce Sync"
    }


@app.post("/sync-now")
def sync_now():
    run_full_sync()
    return {
        "status": "success",
        "message": "Full sync completed"
    }


@app.post("/webhook/woocommerce/order")
async def woocommerce_order_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        return {
            "status": "ignored",
            "message": "No JSON body"
        }

    order_id = payload.get("id")

    if not order_id:
        return {
            "status": "ignored",
            "message": "No order id"
        }

    logger.info(f"WooCommerce webhook received for order: {order_id}")

    background_tasks.add_task(sync_one_order_by_id, order_id)

    return {
        "status": "accepted",
        "message": "Order sync scheduled",
        "order_id": order_id
    }


@app.post("/webhook/erp/item-created")
async def erp_item_created(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception as e:
        return {
            "status": "error",
            "message": f"Invalid JSON payload: {e}"
        }

    logger.info(f"ERP Item Created Webhook payload: {payload}")
    item_code = payload.get("name") or payload.get("item_code")

    if not item_code:
        return {
            "status": "error",
            "message": "No item code received"
        }

    logger.info(f"ERP Item Created: {item_code}")

    background_tasks.add_task(sync_one_product, item_code)

    return {
        "status": "accepted",
        "message": "Product sync scheduled",
        "item_code": item_code
    }


@app.post("/webhook/erp/item-updated")
async def erp_item_updated(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception as e:
        return {
            "status": "error",
            "message": f"Invalid JSON payload: {e}"
        }

    logger.info(f"ERP Item Updated Webhook payload: {payload}")
    item_code = payload.get("name") or payload.get("item_code")

    if not item_code:
        return {
            "status": "error",
            "message": "No item code received"
        }

    logger.info(f"ERP Item Updated: {item_code}")

    background_tasks.add_task(sync_one_product, item_code)

    return {
        "status": "accepted",
        "message": "Product sync scheduled",
        "item_code": item_code
    }  


@app.post("/webhook/erp/item-price-updated")
async def erp_item_price_updated(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception as e:
        return {
            "status": "error",
            "message": f"Invalid JSON payload: {e}"
        }

    logger.info(f"ERP Item Price Updated Webhook payload: {payload}")
    item_code = payload.get("item_code") or payload.get("name")

    if not item_code:
        return {
            "status": "error",
            "message": "No item_code received"
        }

    logger.info(f"ERP Item Price Updated: {item_code}")

    background_tasks.add_task(sync_one_product, item_code)

    return {
        "status": "accepted",
        "message": "Product sync scheduled",
        "item_code": item_code
    }      


@app.post("/webhook/erp/stock-updated")
async def erp_stock_updated(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception as e:
        return {
            "status": "error",
            "message": f"Invalid JSON payload: {e}"
        }

    logger.info(f"ERP Stock Updated Webhook payload: {payload}")
    item_code = payload.get("item_code") or payload.get("name")

    if not item_code:
        return {
            "status": "error",
            "message": "No item_code received"
        }

    logger.info(f"ERP Stock Updated: {item_code}")

    background_tasks.add_task(sync_one_product, item_code)

    return {
        "status": "accepted",
        "message": "Product sync scheduled",
        "item_code": item_code
    }

#@app.on_event("startup")
#def startup_event():
#   sync_thread = threading.Thread(target=run_forever, daemon=True)
#   sync_thread.start()

