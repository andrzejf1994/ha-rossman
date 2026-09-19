"""Constants for the Rossmann integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "rossmann"
NAME = "Rossmann"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
]

WEB_BASE = "https://www.rossmann.pl"
API_BASE = "https://api.rossmann.pl"

AUTH_TOKEN_URL = f"{WEB_BASE}/auth/token"
AUTH_REFRESH_URL = f"{WEB_BASE}/auth/tokens/refreshment"
USER_URL = f"{WEB_BASE}/usr/api/user"
EXTERNAL_TOKEN_URL = f"{WEB_BASE}/auth/external/token"

COUPONS_URL = f"{API_BASE}/nCrm/coupons"
LOYALTY_CARD_URL = f"{API_BASE}/users/{{user_id}}/loyaltyCards"
ORDER_TYPES_URL = f"{API_BASE}/users/{{user_id}}/orders/orderHistoryTypes"

ORDERS_HISTORY_URL = f"{WEB_BASE}/orders/order/grouped-history"
ONLINE_ORDER_URL = f"{WEB_BASE}/orders/order/online/{{order_id}}"
OFFLINE_ORDER_URL = f"{WEB_BASE}/orders/order/offline/{{transaction_id}}"
GO_SAVINGS_URL = f"{WEB_BASE}/scanandgo/api/orders/savings"

COUPON_CATALOG_URL = f"{WEB_BASE}/productscatalog/api/v1/Catalog"
AVAILABILITY_URL = f"{WEB_BASE}/availability/shops/{{shop_number}}/availability"

# Captured from the official Rossmann iOS app 5.110.0.
# This is a private API and Rossmann may require a newer app version in the future.
API_USER_AGENT = "Rossmann/5.110.0 (iPhone; iOS 27.0; Scale/3.00)"
ACCEPT_LANGUAGE = "pl-PL;q=1, en-US;q=0.9"

CONF_TOKEN = "token"
CONF_TOKEN_EXPIRY = "token_expiry"
CONF_USER_ID = "user_id"
CONF_USERNAME = "username"
CONF_AUTO_COUPONS = "auto_coupons"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_RECEIPT_DETAIL_LIMIT = "receipt_detail_limit"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)
DEFAULT_AUTO_COUPONS = False
DEFAULT_RECEIPT_DETAIL_LIMIT = 15
MIN_SCAN_INTERVAL_MINUTES = 5
MAX_SCAN_INTERVAL_MINUTES = 120
MIN_RECEIPT_DETAIL_LIMIT = 5
MAX_RECEIPT_DETAIL_LIMIT = 50

ORDER_PAGE_SIZE = 15
MAX_RECENT_SYNC_PAGES = 5
MAX_BOOTSTRAP_PAGES = 100
MAX_ORDER_CACHE = 1000
MAX_RECEIPT_CACHE = 100

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = f"{DOMAIN}.receipts"

EVENT_NEW_PURCHASE = f"{DOMAIN}_new_purchase"

SERVICE_REFRESH = "refresh"
SERVICE_ACTIVATE_COUPON = "activate_coupon"
SERVICE_GET_COUPON_PRODUCTS = "get_coupon_products"
SERVICE_CHECK_AVAILABILITY = "check_availability"

ATTR_COUPON_ID = "coupon_id"
ATTR_PAGE = "page"
ATTR_PAGE_SIZE = "page_size"
ATTR_SHOP_NUMBER = "shop_number"
ATTR_PRODUCT_IDS = "product_ids"
