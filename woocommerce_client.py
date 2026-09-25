import requests
from config import WC_URL, WC_CONSUMER_KEY, WC_CONSUMER_SECRET
import time
from functools import lru_cache
from utils import logger


DEBUG = False

# Shared session for HTTP connection pooling (keep-alive)
session = requests.Session()
session.params = {
    "consumer_key": WC_CONSUMER_KEY,
    "consumer_secret": WC_CONSUMER_SECRET
}


def wc_request(method, path, **kwargs):
    url = f"{WC_URL}{path}"
    for attempt in range(3):
        try:
            response = session.request(method, url, **kwargs)
            
            if DEBUG:
                print(f"WooCommerce {method} status: {response.status_code}")
                if response.status_code != 200:
                    print(response.text)
                    
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 10))
                logger.warning(f"WooCommerce rate limit hit (429). Attempt {attempt + 1}/3. Retrying in {retry_after} seconds...")
                time.sleep(retry_after)
                continue
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise e
            logger.warning(f"WooCommerce request failed: {e}. Retrying in 2 seconds...")
            time.sleep(2)


def wc_get(path, params=None):
    return wc_request("GET", path, params=params)


def wc_post(path, payload):
    res = wc_request("POST", path, json=payload)
    time.sleep(0.3)
    return res


def wc_put(path, payload):
    res = wc_request("PUT", path, json=payload)
    time.sleep(0.3)
    return res


@lru_cache(maxsize=1024)
def find_product_by_sku(sku):
    products = wc_get(
        "/wp-json/wc/v3/products",
        params={"sku": sku}
    )

    return products[0] if products else None


@lru_cache(maxsize=128)
def find_category_by_name(category_name):
    categories = wc_get(
        "/wp-json/wc/v3/products/categories",
        params={
            "search": category_name,
            "per_page": 100
        }
    )

    for category in categories:
        if category["name"].lower() == category_name.lower():
            return category

    return None


def create_category(category_name):
    payload = {
        "name": category_name
    }
    return wc_post("/wp-json/wc/v3/products/categories", payload)


def get_or_create_category(category_name):
    existing_category = find_category_by_name(category_name)

    if existing_category:
        return existing_category

    new_cat = create_category(category_name)
    find_category_by_name.cache_clear()
    return new_cat