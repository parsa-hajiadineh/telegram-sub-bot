import os
import logging
from supabase import create_client, Client as SupabaseClient

# ============================================
# LOGGING CONFIGURATION
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TelegramBot")

# ============================================
# ENVIRONMENT VARIABLES
# ============================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")
ADMIN2_TELEGRAM_ID = os.getenv("ADMIN2_TELEGRAM_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS", "")
NORMAL_CHANNEL_ID = os.getenv("NORMAL_CHANNEL_ID")
PREMIUM_CHANNEL_ID = os.getenv("PREMIUM_CHANNEL_ID")
TEST_CHANNEL_ID = os.getenv("TEST_CHANNEL_ID")

NORMAL_PRICE = float(os.getenv("NORMAL_PRICE", "5"))
PREMIUM_PRICE = float(os.getenv("PREMIUM_PRICE", "20"))

TETHER_WALLET = os.getenv("TETHER_WALLET", "")
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "")

PORT = int(os.getenv("PORT", "8000"))

# Validation
if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN is missing!")
if not SUPABASE_URL:
    raise SystemExit("❌ SUPABASE_URL is missing!")
if not SUPABASE_KEY:
    raise SystemExit("❌ SUPABASE_KEY is missing!")

REQUIRED_CHANNELS_LIST = [c.strip() for c in REQUIRED_CHANNELS.split(",") if c.strip()]

# ============================================
# SUPABASE INITIALIZATION
# ============================================
try:
    supabase_client: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("✅ Supabase initialized")
except Exception as e:
    logger.exception(f"Failed to initialize Supabase: {e}")
    raise SystemExit("Failed to init Supabase")

# ============================================
# SHEET STRUCTURE DEFINITIONS
# ============================================
SHEET_DEFINITIONS = {
    "Users": [
        "telegram_id", "username", "full_name", "email", 
        "referral_code", "referred_by", "wallet_balance", 
        "status", "created_at", "last_seen", "boost_data",
        "reserved_product", "reserved_amount"
    ],
    "Subscriptions": [
        "telegram_id", "username", "subscription_type", 
        "status", "activated_at", "expires_at", "payment_method"
    ],
    "Purchases": [
        "purchase_id", "telegram_id", "username", "product",
        "amount_usd", "amount_irr", "payment_method", 
        "transaction_id", "admin_action", "status", "created_at", 
        "approved_at", "approved_by", "notes"
    ],
    "Referrals": [
        "referrer_id", "referred_id", "level", 
        "commission_usd", "status", "purchase_id", 
        "created_at", "paid_at"
    ],
    "Withdrawals": [
        "withdrawal_id", "telegram_id", "amount_usd", 
        "method", "wallet_address", "card_number", 
        "status", "requested_at", "processed_at", 
        "processed_by", "notes"
    ],
    "Tickets": [
        "ticket_id", "telegram_id", "username", 
        "subject", "message", "status", 
        "created_at", "response", "responded_at"
    ],
    "Config": [
        "key", "value", "description"
    ],
    "DiscountCodes": [
    "code", "discount_percent", "max_uses", "used_count",
    "valid_until", "created_by", "created_at", "status"
    ],
    "GiftCards": [
    "gift_code", "product", "amount_usd", "buyer_id", 
    "buyer_username", "recipient_id", "recipient_username",
    "message", "status", "created_at", "redeemed_at"
    ],
    "BoostCodes": [
    "code", "level1_percent", "level2_percent", "max_uses",
    "used_count", "valid_until", "created_by", "created_at", "status"
    ],
    "Affiliates": [  # ← شیت جدید
        "telegram_id",      # ID افیلیت
        "username",         # یوزرنیم
        "full_name",        # نام کامل
        "max_depth",        # حداکثر سطح (مثلاً ۱۰)
        "rate_percent",     # نرخ پورسانت برای سطح ۳+ (مثلاً ۵)
        "status",           # active / inactive
        "created_at",       # تاریخ ساخت
        "created_by",       # ادمینی که ساخته
        "notes"             # یادداشت
    ]
}

# ============================================
# TABLE NAME MAPPING
# ============================================
TABLE_MAP = {
    "Users": "users",
    "Subscriptions": "subscriptions",
    "Purchases": "purchases",
    "Referrals": "referrals",
    "Withdrawals": "withdrawals",
    "Tickets": "tickets",
    "Config": "config",
    "DiscountCodes": "discount_codes",
    "GiftCards": "gift_cards",
    "BoostCodes": "boost_codes",
    "Affiliates": "affiliates",
}
