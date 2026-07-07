
"""
Telegram Subscription Bot - Part 1/3
Configuration, Google Sheets, and Core Functions
"""

import os
import json
import time
import asyncio
import logging
import random
import string
import uuid
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.utils.exceptions import (
    MessageToDeleteNotFound, MessageCantBeDeleted,
    MessageNotModified, CantParseEntities
)
import base64
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
INSTANCE_MODE = os.getenv("INSTANCE_MODE", "polling").lower()

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

# ============================================
# DATABASE HELPERS (Supabase)
# ============================================

async def get_all_rows(sheet_name: str) -> List[List[str]]:
    """Get all rows — returns [header_row, row1, row2, ...]
    Each data row has the Supabase internal id appended at the end (index len(headers)).
    """
    try:
        table = TABLE_MAP.get(sheet_name)
        if not table:
            logger.error(f"Unknown sheet: {sheet_name}")
            return []
        headers = SHEET_DEFINITIONS.get(sheet_name, [])
        result = supabase_client.table(table).select("*").order("id").execute()
        rows = [headers]
        for record in result.data:
            row = [str(record.get(h, "") or "") for h in headers]
            row.append(record["id"])  # supabase id at index len(headers)
            rows.append(row)
        return rows
    except Exception as e:
        logger.exception(f"Failed to get rows from {sheet_name}: {e}")
        return []


async def append_row(sheet_name: str, row: List[Any]) -> bool:
    """Insert a new row into the table"""
    try:
        table = TABLE_MAP.get(sheet_name)
        headers = SHEET_DEFINITIONS.get(sheet_name, [])
        if not table or not headers:
            return False
        data = {col: str(row[i]) if i < len(row) and row[i] is not None else ""
                for i, col in enumerate(headers)}
        supabase_client.table(table).insert(data).execute()
        return True
    except Exception as e:
        logger.exception(f"Failed to append row to {sheet_name}: {e}")
        return False


async def update_row(sheet_name: str, row_index: int, row: List[Any]) -> bool:
    """Update an existing row using Supabase id stored at row[len(headers)]"""
    try:
        table = TABLE_MAP.get(sheet_name)
        headers = SHEET_DEFINITIONS.get(sheet_name, [])
        if not table or not headers:
            return False
        supabase_id = row[len(headers)] if len(row) > len(headers) else None
        if supabase_id is None:
            logger.error(f"No supabase id found in row for {sheet_name}")
            return False
        data = {col: str(row[i]) if i < len(row) and row[i] is not None else ""
                for i, col in enumerate(headers)}
        supabase_client.table(table).update(data).eq("id", supabase_id).execute()
        return True
    except Exception as e:
        logger.exception(f"Failed to update row in {sheet_name}: {e}")
        return False


async def find_user(telegram_id: int) -> Optional[Tuple[int, List[str]]]:
    """Find user by telegram_id — returns (supabase_id, row) or None"""
    try:
        result = supabase_client.table("users").select("*").eq(
            "telegram_id", str(telegram_id)
        ).execute()
        if result.data:
            headers = SHEET_DEFINITIONS["Users"]
            record = result.data[0]
            row = [str(record.get(h, "") or "") for h in headers]
            row.append(record["id"])
            return record["id"], row
        return None
    except Exception as e:
        logger.exception(f"Failed to find user {telegram_id}: {e}")
        return None

# ============================================
# BOT INITIALIZATION
# ============================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

user_states = {}
_last_bot_messages = {}

# ============================================
# MIDDLEWARE: Channel Membership Check
# ============================================
async def check_membership_for_all_messages(message: types.Message):
    """Check if user is still member of required channels"""
    user = message.from_user
    
    # فقط برای پیام‌های متنی که دستور /start نیستن
    if not message.text or message.text.startswith("/start"):
        return True
    
    is_member, missing = await check_required_channels(user.id)
    
    if not is_member:
        kb = channel_membership_keyboard(missing)
        await send_and_record(
            user.id,
            "⚠️ <b>شما از کانال خارج شده‌اید!</b>\n\n"
            "برای ادامه استفاده از ربات باید دوباره عضو شوید.",
            parse_mode="HTML",
            reply_markup=kb
        )
        return False
    
    return True


# ============================================
# UTILITY FUNCTIONS
# ============================================
def now_iso() -> str:
    """Get current time in ISO format"""
    return datetime.utcnow().replace(microsecond=0).isoformat()

def parse_iso(date_str: str) -> Optional[datetime]:
    """Parse ISO date string"""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except:
        return None

def generate_referral_code(length: int = 6) -> str:
    """Generate unique referral code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_purchase_id() -> str:
    """Generate unique purchase ID"""
    return f"PUR{int(time.time())}{random.randint(1000, 9999)}"

def generate_ticket_id() -> str:
    """Generate unique ticket ID"""
    return f"TKT{uuid.uuid4().hex[:8].upper()}"

def generate_withdrawal_id() -> str:
    """Generate unique withdrawal ID"""
    return f"WDR{int(time.time())}{random.randint(1000, 9999)}"

def is_valid_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def is_admin(user_id: int) -> bool:
    """Check if user is admin (اصلی یا دوم)"""
    try:
        if str(user_id) == str(ADMIN_TELEGRAM_ID):
            return True
        if ADMIN2_TELEGRAM_ID and str(user_id) == str(ADMIN2_TELEGRAM_ID):
            return True
        return False
    except:
        return False

# ============================================
# NOBITEX API FOR IRR PRICE
# ============================================
async def get_usdt_price_irr() -> float:
    """
    Get USDT price in IRR
    اول از Config sheet میخونه، اگه نبود fallback به Nobitex API
    """
    try:
        # ✅ اول از Google Sheet بخون
        config_rows = await get_all_rows("Config")
        
        for row in config_rows[1:]:
            if not row or len(row) < 2:
                continue
            
            key = row[0].strip() if len(row) > 0 else ""
            value = row[1].strip() if len(row) > 1 else ""
            
            if key == "usdt_price_irr" and value:
                try:
                    price = float(value)
                    logger.info(f"💱 USDT (از Config): {price:,.0f} تومان")
                    return price
                except:
                    pass
        
        # اگه توی Config نبود، سعی کن از Nobitex بگیر
        logger.info("💱 قیمت USDT در Config نبود، Nobitex...")
        
        async with ClientSession() as session:
            async with session.get("https://api.nobitex.ir/v2/orderbook/USDTIRT", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    asks = data.get("asks", [])
                    if asks and len(asks) > 0:
                        price_rial = float(asks[0][0])
                        price_toman = price_rial / 10
                        logger.info(f"💱 USDT (از Nobitex): {price_toman:,.0f} تومان")
                        return price_toman
    except Exception as e:
        logger.exception(f"Nobitex/Config error: {e}")
    
    # Fallback نهایی
    logger.warning("⚠️ Using fallback USDT price: 160,000 تومان")
    return 160000.0


# 

async def get_usdt_price_from_config() -> float:
    """دریافت قیمت USDT از Config"""
    try:
        config_rows = await get_all_rows("Config")
        
        for row in config_rows[1:]:
            if not row or len(row) < 2:
                continue
            
            if row[0].strip() == "usdt_price_irr":
                return float(row[1].strip())
        
        return 160000.0  # پیش‌فرض
    except:
        return 160000.0


async def set_usdt_price_in_config(new_price: float) -> bool:
    """تنظیم قیمت USDT در Config"""
    try:
        config_rows = await get_all_rows("Config")
        
        # پیدا کردن ردیف موجود
        for idx, row in enumerate(config_rows[1:], start=2):
            if not row or len(row) < 1:
                continue
            
            if row[0].strip() == "usdt_price_irr":
                # آپدیت
                row[1] = str(new_price)
                if len(row) < 3:
                    row.append("قیمت تتر به تومان (دستی)")
                await update_row("Config", idx, row)
                logger.info(f"✅ USDT price updated to {new_price:,.0f}")
                return True
        
        # اگه نبود، اضافه کن
        await append_row("Config", [
            "usdt_price_irr",
            str(new_price),
            "قیمت تتر به تومان (دستی)"
        ])
        logger.info(f"✅ USDT price created: {new_price:,.0f}")
        return True
        
    except Exception as e:
        logger.exception(f"Error setting USDT price: {e}")
        return False



# 

# ============================================
# TELEGRAM HELPERS
# ============================================
async def safe_delete_message(chat_id: int, message_id: int):
    """Safely delete message"""
    try:
        await bot.delete_message(chat_id, message_id)
    except (MessageToDeleteNotFound, MessageCantBeDeleted):
        pass
    except Exception:
        pass

async def send_and_record(user_id: int, text: str, **kwargs):
    """Send message and record for later deletion"""
    try:
        prev_msg_id = _last_bot_messages.get(user_id)
        if prev_msg_id:
            await safe_delete_message(user_id, prev_msg_id)
        
        msg = await bot.send_message(user_id, text, **kwargs)
        _last_bot_messages[user_id] = msg.message_id
        return msg
    except Exception as e:
        logger.exception(f"Failed to send message to {user_id}: {e}")
        return None

async def is_member_of_channel(channel_id: str, user_id: int) -> bool:
    """Check if user is member of channel"""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status not in ("left", "kicked")
    except Exception:
        return False

async def check_required_channels(user_id: int) -> Tuple[bool, List[str]]:
    """Check if user is member of all required channels"""
    if not REQUIRED_CHANNELS_LIST:
        return True, []
    
    missing = []
    for channel in REQUIRED_CHANNELS_LIST:
        if not await is_member_of_channel(channel, user_id):
            missing.append(channel)
    
    return len(missing) == 0, missing

async def create_invite_link(channel_id: str, expire_minutes: int = 60) -> Optional[str]:
    """Create temporary invite link"""
    try:
        expire_date = int((datetime.utcnow() + timedelta(minutes=expire_minutes)).timestamp())
        link = await bot.create_chat_invite_link(
            chat_id=channel_id,
            expire_date=expire_date,
            member_limit=1
        )
        return link.invite_link
    except Exception as e:
        logger.exception(f"Failed to create invite link: {e}")
        return None

async def remove_from_channel(channel_id: str, user_id: int) -> bool:
    """Remove user from channel"""
    try:
        await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
        await asyncio.sleep(0.5)
        await bot.unban_chat_member(chat_id=channel_id, user_id=user_id)
        logger.info(f"✅ Removed user {user_id} from {channel_id}")
        return True
    except Exception as e:
        logger.exception(f"Failed to remove: {e}")
        return False

# ============================================
# USER MANAGEMENT
# ============================================
async def create_or_update_user(user: types.User, email: str = None) -> Tuple[int, List[str]]:
    """Create or update user"""
    result = await find_user(user.id)
    
    if result:
        row_idx, row_data = result
        row_data[1] = user.username or ""
        row_data[2] = user.full_name or ""
        row_data[9] = now_iso()
        
        if email and not row_data[3]:
            row_data[3] = email
        
        await update_row("Users", row_idx, row_data)
        return row_idx, row_data
    else:
        new_row = [
            str(user.id),
            user.username or "",
            user.full_name or "",
            email or "",
            generate_referral_code(),
            "",
            "0",
            "active",
            now_iso(),
            now_iso()
        ]
        
        await append_row("Users", new_row)
        rows = await get_all_rows("Users")
        return len(rows), new_row

async def get_user_balance(telegram_id: int) -> float:
    """Get user wallet balance"""
    result = await find_user(telegram_id)
    if result:
        _, row = result
        try:
            return float(row[6]) if len(row) > 6 else 0.0
        except:
            return 0.0
    return 0.0

async def update_user_balance(telegram_id: int, amount: float, add: bool = True):
    """Update user wallet balance"""
    result = await find_user(telegram_id)
    if result:
        row_idx, row = result
        try:
            current = float(row[6]) if len(row) > 6 else 0.0
        except:
            current = 0.0
        
        if add:
            current += amount
        else:
            current -= amount
        
        row[6] = str(max(0, current))
        await update_row("Users", row_idx, row)

async def get_active_subscription(telegram_id: int) -> Optional[List[str]]:
    """Get user's active subscription"""
    rows = await get_all_rows("Subscriptions")
    now = datetime.utcnow()
    
    for row in rows[1:]:
        if row and str(row[0]) == str(telegram_id):
            status = row[3] if len(row) > 3 else ""
            expires_str = row[5] if len(row) > 5 else ""
            
            if status == "active":
                expires = parse_iso(expires_str)
                if expires and expires > now:
                    return row
    
    return None

async def get_user_reserve_status(telegram_id: int) -> dict:
    """
    چک وضعیت رزرو کاربر
    Returns: {"has_reserve": bool, "product": str, "amount_paid": float}
    """
    try:
        result = await find_user(telegram_id)
        if not result:
            return {"has_reserve": False, "product": "", "amount_paid": 0.0}
        
        _, row = result
        
        reserved_product = row[11] if len(row) > 11 else ""
        reserved_amount = float(row[12]) if len(row) > 12 and row[12] else 0.0
        
        return {
            "has_reserve": bool(reserved_product and reserved_amount > 0),
            "product": reserved_product,
            "amount_paid": reserved_amount
        }
    except Exception as e:
        logger.exception(f"Error getting reserve status: {e}")
        return {"has_reserve": False, "product": "", "amount_paid": 0.0}


async def set_user_reserve(telegram_id: int, product: str, amount_paid: float) -> bool:
    """ثبت رزرو برای کاربر"""
    try:
        result = await find_user(telegram_id)
        if not result:
            return False
        
        row_idx, row = result
        
        # اطمینان از وجود فیلدها
        while len(row) < 13:
            row.append("")
        
        row[11] = product  # reserved_product
        row[12] = str(amount_paid)  # reserved_amount
        
        await update_row("Users", row_idx, row)
        logger.info(f"✅ Reserve set for {telegram_id}: {product} / ${amount_paid}")
        return True
        
    except Exception as e:
        logger.exception(f"Error setting reserve: {e}")
        return False


async def clear_user_reserve(telegram_id: int) -> bool:
    """پاک کردن رزرو (بعد از تکمیل)"""
    try:
        result = await find_user(telegram_id)
        if not result:
            return False
        
        row_idx, row = result
        
        while len(row) < 13:
            row.append("")
        
        row[11] = ""  # reserved_product
        row[12] = ""  # reserved_amount
        
        await update_row("Users", row_idx, row)
        logger.info(f"✅ Reserve cleared for {telegram_id}")
        return True
        
    except Exception as e:
        logger.exception(f"Error clearing reserve: {e}")
        return False

async def is_affiliate(telegram_id: int) -> bool:
    """چک اگه این کاربر افیلیت هست"""
    try:
        rows = await get_all_rows("Affiliates")
        
        for row in rows[1:]:
            if not row or len(row) < 6:
                continue
            
            if str(row[0]) == str(telegram_id) and row[5] == "active":
                return True
        
        return False
    except:
        return False


async def get_affiliate_config(telegram_id: int) -> dict:
    """
    دریافت تنظیمات افیلیت
    Returns: {"is_affiliate": bool, "max_depth": int, "rate": float}
    """
    try:
        rows = await get_all_rows("Affiliates")
        
        for row in rows[1:]:
            if not row or len(row) < 6:
                continue
            
            if str(row[0]) == str(telegram_id) and row[5] == "active":
                return {
                    "is_affiliate": True,
                    "max_depth": int(row[3]) if len(row) > 3 and row[3] else 10,
                    "rate": float(row[4]) if len(row) > 4 and row[4] else 5.0
                }
        
        return {"is_affiliate": False, "max_depth": 0, "rate": 0.0}
        
    except Exception as e:
        logger.exception(f"Error getting affiliate config: {e}")
        return {"is_affiliate": False, "max_depth": 0, "rate": 0.0}


async def create_affiliate(telegram_id: int, max_depth: int, rate_percent: float, created_by: int, notes: str = "") -> bool:
    """ساخت افیلیت جدید"""
    try:
        # چک تکراری
        rows = await get_all_rows("Affiliates")
        for row in rows[1:]:
            if row and str(row[0]) == str(telegram_id):
                return False  # قبلاً وجود داره
        
        # دریافت اطلاعات کاربر
        user_result = await find_user(telegram_id)
        username = ""
        full_name = ""
        
        if user_result:
            _, user_row = user_result
            username = user_row[1] if len(user_row) > 1 else ""
            full_name = user_row[2] if len(user_row) > 2 else ""
        
        # ساخت افیلیت
        await append_row("Affiliates", [
            str(telegram_id),
            username,
            full_name,
            str(max_depth),
            str(rate_percent),
            "active",
            now_iso(),
            str(created_by),
            notes
        ])
        
        logger.info(f"✅ Affiliate created: {telegram_id} | depth={max_depth} | rate={rate_percent}%")
        return True
        
    except Exception as e:
        logger.exception(f"Error creating affiliate: {e}")
        return False


async def update_affiliate(telegram_id: int, max_depth: int = None, rate_percent: float = None) -> bool:
    """آپدیت تنظیمات افیلیت"""
    try:
        rows = await get_all_rows("Affiliates")
        
        for idx, row in enumerate(rows[1:], start=2):
            if not row or str(row[0]) != str(telegram_id):
                continue
            
            # آپدیت فیلدها
            if max_depth is not None:
                row[3] = str(max_depth)
            
            if rate_percent is not None:
                row[4] = str(rate_percent)
            
            await update_row("Affiliates", idx, row)
            logger.info(f"✅ Affiliate updated: {telegram_id} | depth={max_depth} | rate={rate_percent}%")
            return True
        
        return False  # پیدا نشد
        
    except Exception as e:
        logger.exception(f"Error updating affiliate: {e}")
        return False


async def deactivate_affiliate(telegram_id: int) -> bool:
    """غیرفعال کردن افیلیت"""
    try:
        rows = await get_all_rows("Affiliates")
        
        for idx, row in enumerate(rows[1:], start=2):
            if not row or str(row[0]) != str(telegram_id):
                continue
            
            row[5] = "inactive"
            await update_row("Affiliates", idx, row)
            logger.info(f"✅ Affiliate deactivated: {telegram_id}")
            return True
        
        return False
        
    except Exception as e:
        logger.exception(f"Error deactivating affiliate: {e}")
        return False



# ============================================
# PART 1 COMPLETE - Continue to Part 2
# ============================================
"""
Telegram Subscription Bot - Part 2/3
Keyboards, Command Handlers, and Payment Processing

⚠️ این فایل ادامه بخش 1 است - در انتهای فایل main.py قرار دهید
"""

# ============================================
# KEYBOARDS
# ============================================
def main_menu_keyboard():
    """Main menu keyboard"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(
        KeyboardButton("🆓 تست کانال"),
        KeyboardButton("💎 خرید اشتراک")
    )
    kb.row(
        KeyboardButton("💰 کیف پول"),
        KeyboardButton("🎁 دعوت دوستان")
    )
    kb.row(
        KeyboardButton("💬 پشتیبانی"),
        KeyboardButton("📚 راهنما")
    )
    return kb

def admin_menu_keyboard():
    """منوی اختصاصی ادمین"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(
        KeyboardButton("📊 آمار سیستم"),
        KeyboardButton("📢 ارسال پیام")
    )
    kb.row(
        KeyboardButton("💳 تایید خریدها"),
        KeyboardButton("💸 تایید برداشت‌ها")
    )
    kb.row(
        KeyboardButton("🎟 کدهای تخفیف"),
        KeyboardButton("🌟 کدهای بوست")
    )
    kb.row(
        KeyboardButton("👤 جستجوی کاربر"),
        KeyboardButton("💱 قیمت تتر")
    )
    kb.row(
        KeyboardButton("💎 افیلیت‌ها"),  # ← دکمه جدید (مخفی)
        KeyboardButton("🔙 منوی عادی")
    )
    return kb


# 

def subscription_keyboard():
    """Subscription purchase keyboard"""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            f"⭐️ اشتراک معمولی - ${NORMAL_PRICE}",
            callback_data="buy_normal"
        ),
        InlineKeyboardButton(
            f"💎 اشتراک ویژه - ${PREMIUM_PRICE}",
            callback_data="buy_premium"
        ),
        InlineKeyboardButton(
            "💵 پیش‌پرداخت $2 (رزرو)",  # ← دکمه جدید
            callback_data="buy_reserve"
        ),
        InlineKeyboardButton("🎁 خرید هدیه", callback_data="buy_gift"),
        InlineKeyboardButton("🎟 کد تخفیف دارم", callback_data="enter_discount"),
        InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")
    )
    return kb


# 

def payment_method_keyboard(product: str):
    """Payment method selection"""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("💳 کارت بانکی", callback_data=f"pay_card_{product}"),
        InlineKeyboardButton("🪙 تتر USDT", callback_data=f"pay_usdt_{product}"),
        InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_buy")
    )
    return kb


def wallet_keyboard(balance: float, has_reserve: bool = False):
    """Wallet keyboard"""
    kb = InlineKeyboardMarkup(row_width=1)
    
    # ✅ اگه رزرو داره، دکمه تکمیل
    if has_reserve:
        kb.add(InlineKeyboardButton("💵 تکمیل پیش‌پرداخت", callback_data="complete_reserve"))
    
    if balance >= 10:
        kb.add(InlineKeyboardButton("💸 برداشت پورسانت", callback_data="withdraw"))
    
    kb.add(
        InlineKeyboardButton("📊 تاریخچه", callback_data="wallet_history"),
        InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")
    )
    return kb


def withdrawal_method_keyboard():
    """Withdrawal method selection"""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("💳 کارت بانکی", callback_data="withdraw_card"),
        InlineKeyboardButton("🪙 تتر USDT", callback_data="withdraw_usdt"),
        InlineKeyboardButton("🔙 بازگشت", callback_data="wallet")
    )
    return kb

def channel_membership_keyboard(missing_channels: List[str]):
    """Keyboard for joining channels"""
    kb = InlineKeyboardMarkup(row_width=1)
    
    for channel in missing_channels:
        # حذف @ اگه وجود داره
        channel_clean = channel.lstrip("@")
        
        kb.add(InlineKeyboardButton(
            f"📢 عضویت در @{channel_clean}",
            url=f"https://t.me/{channel_clean}"
        ))
    
    kb.add(InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership"))
    return kb

def admin_purchase_keyboard(purchase_id: str, user_id: int):
    """Admin keyboard for purchase approval"""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ تایید", callback_data=f"approve_{purchase_id}_{user_id}"),
        InlineKeyboardButton("❌ رد", callback_data=f"reject_{purchase_id}_{user_id}")
    )
    return kb

def admin_withdrawal_keyboard(withdrawal_id: str, user_id: int):
    """Admin keyboard for withdrawal approval"""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ پرداخت شد", callback_data=f"approve_wd_{withdrawal_id}_{user_id}"),
        InlineKeyboardButton("❌ رد", callback_data=f"reject_wd_{withdrawal_id}_{user_id}")
    )
    return kb

def social_share_keyboard(product: str = "subscription") -> InlineKeyboardMarkup:
    """Social media share buttons"""
    kb = InlineKeyboardMarkup(row_width=2)
    
    bot_username = os.getenv("BOT_USERNAME", "YourBot")  # اضافه کن به ENV
    share_text = f"🎉 من اشتراک {product} گرفتم! شما هم امتحان کنید:"
    share_url = f"https://t.me/{bot_username}"
    
    # URL encode
    import urllib.parse
    encoded_text = urllib.parse.quote(share_text)
    encoded_url = urllib.parse.quote(share_url)
    
    kb.add(
        InlineKeyboardButton(
            "📱 تلگرام",
            url=f"https://t.me/share/url?url={encoded_url}&text={encoded_text}"
        ),
        InlineKeyboardButton(
            "💬 واتساپ",
            url=f"https://wa.me/?text={encoded_text}%20{encoded_url}"
        )
    )
    kb.add(
        InlineKeyboardButton(
            "🐦 توییتر",
            url=f"https://twitter.com/intent/tweet?text={encoded_text}&url={encoded_url}"
        ),
        InlineKeyboardButton(
            "📘 فیسبوک",
            url=f"https://www.facebook.com/sharer/sharer.php?u={encoded_url}"
        )
    )
    kb.add(
        InlineKeyboardButton("✅ تمام", callback_data="close_share")
    )
    
    return kb


async def get_user_max_purchase(telegram_id: int) -> float:
    """
    دریافت بالاترین مبلغ خرید تایید شده کاربر
    Returns: مبلغ به دلار (float)
    """
    try:
        purchases_rows = await get_all_rows("Purchases")
        max_purchase = 0.0
        
        for row in purchases_rows[1:]:
            if not row or len(row) < 9:
                continue
            
            # چک اگه این خرید برای این کاربر و تایید شده
            if str(row[1]) == str(telegram_id) and row[9] == "approved":
                try:
                    amount = float(row[4]) if len(row) > 4 and row[4] else 0.0
                    if amount > max_purchase:
                        max_purchase = amount
                except:
                    pass
        
        return max_purchase
        
    except Exception as e:
        logger.exception(f"Error getting max purchase for {telegram_id}: {e}")
        return 0.0


# 
async def check_reserve_block(message: types.Message) -> bool:
    """
    چک اگه کاربر رزرو داره، دکمه‌ها غیرفعال
    Returns: True اگه بلاک نشد (ادامه بده)
             False اگه بلاک شد (متوقف کن)
    """
    user = message.from_user
    
    # دکمه‌هایی که باید بلاک بشن
    blocked_buttons = [
        "🆓 تست کانال",
        "💎 خرید اشتراک",
        "🎁 دعوت دوستان",
        "📚 راهنما"
    ]
    
    if message.text not in blocked_buttons:
        return True  # این دکمه بلاک نمیشه
    
    reserve = await get_user_reserve_status(user.id)
    
    if not reserve["has_reserve"]:
        return True  # رزرو نداره، ادامه بده
    
    # ✅ رزرو داره! بلاک کن
    product_name = "ویژه" if reserve["product"] == "premium" else "معمولی"
    paid = reserve["amount_paid"]
       
    total_price = PREMIUM_PRICE if reserve["product"] == "premium" else NORMAL_PRICE
    remaining = total_price - paid
    
    await send_and_record(
        massage.from_user.id,
        f"⏳ <b>پیش‌پرداخت فعال</b>\n\n"
        f"شما رزرو انجام داده‌اید:\n"
        f"📦 محصول: اشتراک {product_name}\n"
        f"💵 پرداخت شده: <b>${paid:.2f}</b>\n"
        f"💰 باقیمانده: <b>${remaining:.2f}</b>\n\n"
        f"⚠️ برای استفاده از ربات، ابتدا باید پرداخت را تکمیل کنید.\n\n"
        f"💡 برای تکمیل، از منوی 💰 کیف پول → تکمیل پیش‌پرداخت استفاده کنید.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )
    
    return False  # بلاک شد



async def get_referral_chain(telegram_id: int, max_levels: int = 20) -> list:
    """
    دریافت زنجیره معرف‌ها از کاربر به سطح بالا
    Returns: [{"level": 1, "referrer_id": "123"}, {"level": 2, "referrer_id": "456"}, ...]
    """
    try:
        chain = []
        current_id = telegram_id
        level = 1
        visited = set()
        visited.add(telegram_id)
        
        users_rows = await get_all_rows("Users")
        
        while level <= max_levels:

            # پیدا کردن referrer فعلی
            referrer_id = None
            
            for row in users_rows[1:]:
                if not row or str(row[0]) != str(current_id):
                    continue
                
                referrer_id = row[5] if len(row) > 5 and row[5] else None
                break
            
            # اگه referrer نداره یا قبلاً دیده شده، تموم شد
            if not referrer_id or int(referrer_id) in visited:
                break
            
            visited.add(int(referrer_id))
            
            chain.append({
                "level": level,
                "referrer_id": referrer_id
            })
            
            current_id = int(referrer_id)
            level += 1

        
        return chain
        
    except Exception as e:
        logger.exception(f"Error getting referral chain: {e}")
        return []


    
# ============================================
# REFERRAL SYSTEM
# ============================================
async def process_referral_commission(purchase_id: str, buyer_id: int, amount_usd: float):
    """
    Process referral commissions - با پشتیبانی افیلیت عمیق
    سطح ۱ و ۲: مثل همیشه (۸% و ۱۲% یا بوست)
    سطح ۳+: فقط برای افیلیت‌ها
    """
    buyer_result = await find_user(buyer_id)
    if not buyer_result:
        return
    
    _, buyer_row = buyer_result
    referrer_id = buyer_row[5] if len(buyer_row) > 5 else ""
    
    if not referrer_id:
        return
    
    # ✅ دریافت سقف خرید referrer سطح ۱
    referrer_max_purchase = await get_user_max_purchase(int(referrer_id))
    cappable_amount = min(amount_usd, referrer_max_purchase) if referrer_max_purchase > 0 else 0
    
    if cappable_amount <= 0:
        logger.info(f"⚠️ Referrer {referrer_id} has no purchase, skipping")
        return
    
    # ═══════════════════════════════════════════════════════
    # Level 1: سطح اول (مثل قبل)
    # ═══════════════════════════════════════════════════════
    referrer_boost = await get_user_boost(int(referrer_id))
    
    if referrer_boost:
        level1_rate = referrer_boost["level1"] / 100
    else:
        level1_rate = 0.08
    
    level1_commission = cappable_amount * level1_rate
    
    await update_user_balance(int(referrer_id), level1_commission, add=True)
    
    await append_row("Referrals", [
        str(referrer_id),
        str(buyer_id),
        "1",
        str(level1_commission),
        "paid",
        purchase_id,
        now_iso(),
        now_iso()
    ])
    
    # Notify
    try:
        cap_note = ""
        if amount_usd > referrer_max_purchase:
            cap_note = f"\n\n💡 پورسانت تا سقف خرید شما (${referrer_max_purchase}) محاسبه شد."
        
        await bot.send_message(
            int(referrer_id),
            f"🎉 <b>پورسانت جدید!</b>\n\n"
            f"💰 مبلغ: <b>${level1_commission:.2f}</b>\n"
            f"👤 از: <code>{buyer_id}</code>\n"
            f"📊 نرخ: {int(level1_rate * 100)}%{cap_note}",
            parse_mode="HTML"
        )
    except:
        pass
    
    # بوست خودکار
    asyncio.create_task(check_and_grant_auto_boost(int(referrer_id)))
    
    # ═══════════════════════════════════════════════════════
    # Level 2: سطح دوم (مثل قبل)
    # ═══════════════════════════════════════════════════════
    referrer_result = await find_user(int(referrer_id))
    if referrer_result:
        _, referrer_row = referrer_result
        level2_referrer_id = referrer_row[5] if len(referrer_row) > 5 else ""
        
        if level2_referrer_id and level2_referrer_id != str(buyer_id):
            # سقف سطح ۲
            level2_max_purchase = await get_user_max_purchase(int(level2_referrer_id))
            level2_cappable_amount = min(amount_usd, level2_max_purchase) if level2_max_purchase > 0 else 0
            
            if level2_cappable_amount > 0:
                # نرخ
                level2_boost = await get_user_boost(int(level2_referrer_id))
                
                if level2_boost:
                    level2_rate = level2_boost["level2"] / 100
                else:
                    level2_rate = 0.12
                
                level2_commission = level2_cappable_amount * level2_rate
                await update_user_balance(int(level2_referrer_id), level2_commission, add=True)
                
                await append_row("Referrals", [
                    str(level2_referrer_id),
                    str(buyer_id),
                    "2",
                    str(level2_commission),
                    "paid",
                    purchase_id,
                    now_iso(),
                    now_iso()
                ])
                
                try:
                    cap_note_l2 = ""
                    if amount_usd > level2_max_purchase:
                        cap_note_l2 = f"\n\n💡 پورسانت تا سقف خرید شما (${level2_max_purchase}) محاسبه شد."
                    
                    boost_badge = "🌟 " if level2_boost else ""
                    await bot.send_message(
                        int(level2_referrer_id),
                        f"🎉 <b>پورسانت سطح 2!</b>{boost_badge}\n\n"
                        f"💰 مبلغ: <b>${level2_commission:.2f}</b>\n"
                        f"📊 نرخ: <b>{int(level2_rate * 100)}%</b>\n"
                        f"👤 از: <code>{buyer_id}</code>{cap_note_l2}",
                        parse_mode="HTML"
                    )
                except:
                    pass
    
    # ═══════════════════════════════════════════════════════
    # Level 3+: افیلیت‌های عمیق (جدید!)
    # ═══════════════════════════════════════════════════════
    # دریافت زنجیره کامل
    chain = await get_referral_chain(buyer_id, max_levels=50)
    
    # پردازش سطح ۳ به بعد
    for item in chain[2:]:  # از سطح ۳ شروع کن (index 2)
        level = item["level"]
        referrer_id = item["referrer_id"]
        
        # چک اگه افیلیت هست
        affiliate_config = await get_affiliate_config(int(referrer_id))
        
        if not affiliate_config["is_affiliate"]:
            continue  # افیلیت نیست، بعدی
        
        # چک عمق مجاز
        if level > affiliate_config["max_depth"]:
            break  # از حد مجاز گذشته، تموم
        
        # محاسبه پورسانت
        # سقف: بالاترین خرید این افیلیت
        affiliate_max_purchase = await get_user_max_purchase(int(referrer_id))
        affiliate_cappable = min(amount_usd, affiliate_max_purchase) if affiliate_max_purchase > 0 else 0
        
        if affiliate_cappable <= 0:
            continue  # خریدی نداره
        
        rate = affiliate_config["rate"] / 100
        commission = affiliate_cappable * rate
        
        # پرداخت
        await update_user_balance(int(referrer_id), commission, add=True)
        
        await append_row("Referrals", [
            str(referrer_id),
            str(buyer_id),
            str(level),  # سطح ۳، ۴، ۵، ...
            str(commission),
            "paid",
            purchase_id,
            now_iso(),
            now_iso()
        ])
        
        # نوتیف (مخفی - فقط به افیلیت)
        try:
            await bot.send_message(
                int(referrer_id),
                f"💎 <b>پورسانت افیلیت سطح {level}!</b>\n\n"
                f"💰 مبلغ: <b>${commission:.2f}</b>\n"
                f"📊 نرخ: <b>{int(rate * 100)}%</b>\n"
                f"👤 از: <code>{buyer_id}</code>\n\n"
                f"🔐 شما افیلیت ویژه هستید!",
                parse_mode="HTML"
            )
        except:
            pass
        
        logger.info(f"✅ Deep affiliate commission: Level {level} → {referrer_id} = ${commission:.2f}")

# 
# ============================================
# SUBSCRIPTION MANAGEMENT
# ============================================
async def activate_subscription(telegram_id: int, username: str, product: str, payment_method: str):
    """Activate subscription"""
    now = now_iso()
    expires = datetime.utcnow() + timedelta(days=180)
    expires_iso = expires.replace(microsecond=0).isoformat()
    
    rows = await get_all_rows("Subscriptions")
    found = False
    
    for idx, row in enumerate(rows[1:], start=2):
        if row and str(row[0]) == str(telegram_id):
            row[1] = username
            row[2] = product
            row[3] = "active"
            row[4] = now
            row[5] = expires_iso
            row[6] = payment_method
            
            await update_row("Subscriptions", idx, row)
            found = True
            break
    
    if not found:
        await append_row("Subscriptions", [
            str(telegram_id),
            username,
            product,
            "active",
            now,
            expires_iso,
            payment_method
        ])
    
    result = await find_user(telegram_id)
    if result:
        row_idx, row = result
        row[7] = "active"
        await update_row("Users", row_idx, row)
    
    channels = [PREMIUM_CHANNEL_ID, NORMAL_CHANNEL_ID] if product == "premium" else [NORMAL_CHANNEL_ID]
    
    for channel in channels:
        if channel:
            link = await create_invite_link(channel, expire_minutes=1440)
            if link:
                try:
                    await bot.send_message(
                        telegram_id,
                        f"🎊 <b>لینک عضویت کانال:</b>\n\n"
                        f"{link}\n\n"
                        f"⏰ این لینک ۲۴ ساعت معتبر است.",
                        parse_mode="HTML"
                    )
                except:
                    pass
    
    delay = (expires - datetime.utcnow()).total_seconds()
    asyncio.create_task(schedule_expiry(telegram_id, channels, delay))
    asyncio.create_task(schedule_expiry_reminders(telegram_id, expires))


async def schedule_expiry(telegram_id: int, channels: List[str], delay: float):
    """Schedule subscription expiry"""
    try:
        await asyncio.sleep(delay)
        
        for channel in channels:
            if channel:
                await remove_from_channel(channel, telegram_id)
        
        rows = await get_all_rows("Subscriptions")
        for idx, row in enumerate(rows[1:], start=2):
            if row and str(row[0]) == str(telegram_id):
                row[3] = "expired"
                await update_row("Subscriptions", idx, row)
                break
        
        try:
            await bot.send_message(
                telegram_id,
                "⏰ <b>اشتراک شما به پایان رسید!</b>\n\n"
                "برای تمدید از منوی خرید استفاده کنید.\n\n"
                "💡 با دعوت دوستان پورسانت کسب کنید!",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard()
            )
        except:
            pass
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception(f"Error in expiry: {e}")

async def schedule_expiry_reminders(telegram_id: int, expires: datetime):
    """Schedule expiry reminder notifications"""
    try:
        now = datetime.utcnow()
        
        # محاسبه زمان‌های یادآوری
        seven_days_before = (expires - timedelta(days=7) - now).total_seconds()
        three_days_before = (expires - timedelta(days=3) - now).total_seconds()
        one_day_before = (expires - timedelta(days=1) - now).total_seconds()
        
        # یادآوری ۷ روز مانده
        if seven_days_before > 0:
            await asyncio.sleep(seven_days_before)
            try:
                await bot.send_message(
                    telegram_id,
                    "⏰ <b>یادآوری اشتراک</b>\n\n"
                    "۷ روز دیگر اشتراک شما به پایان می‌رسد.\n\n"
                    "💡 برای تمدید از منوی 💎 خرید اشتراک استفاده کنید.\n\n"
                    "🎁 با دعوت دوستان، پورسانت کسب کنید و رایگان تمدید کنید!",
                    parse_mode="HTML"
                )
            except:
                pass
        
        # یادآوری ۳ روز مانده
        if three_days_before > 0:
            await asyncio.sleep(max(0, three_days_before - seven_days_before))
            try:
                await bot.send_message(
                    telegram_id,
                    "⚠️ <b>هشدار انقضا</b>\n\n"
                    "فقط <b>۳ روز</b> تا پایان اشتراک شما باقی مانده!\n\n"
                    "💎 همین الان تمدید کنید تا از کانال‌ها خارج نشوید.",
                    parse_mode="HTML"
                )
            except:
                pass
        
        # یادآوری ۱ روز مانده
        if one_day_before > 0:
            await asyncio.sleep(max(0, one_day_before - three_days_before))
            try:
                await bot.send_message(
                    telegram_id,
                    "🔴 <b>هشدار نهایی!</b>\n\n"
                    "فقط <b>۱ روز</b> تا پایان اشتراک شما!\n\n"
                    "⏰ فردا از کانال‌ها حذف می‌شوید.\n\n"
                    "💎 الان تمدید کنید!",
                    parse_mode="HTML",
                    reply_markup=subscription_keyboard()
                )
            except:
                pass
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception(f"Error in expiry reminders: {e}")


async def generate_monthly_report(telegram_id: int) -> str:
    """Generate monthly activity report for user"""
    try:
        # دریافت اطلاعات کاربر
        user_result = await find_user(telegram_id)
        if not user_result:
            return None
        
        _, user_row = user_result
        username = user_row[1] if len(user_row) > 1 else "کاربر"
        
        # محاسبه تعداد معرفی‌های ماه جاری
        referrals_rows = await get_all_rows("Referrals")
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        monthly_referrals = 0
        monthly_earnings = 0.0
        
        for row in referrals_rows[1:]:
            if not row or len(row) < 7:
                continue
            
            if str(row[0]) != str(telegram_id):
                continue
            
            created_at = parse_iso(row[6]) if len(row) > 6 else None
            if created_at and created_at >= month_start:
                monthly_referrals += 1
                try:
                    monthly_earnings += float(row[3]) if len(row) > 3 else 0
                except:
                    pass
        
        # محاسبه کل معرفی‌ها و درآمد
        total_referrals = sum(1 for row in referrals_rows[1:] if row and str(row[0]) == str(telegram_id))
        total_earnings = 0.0
        for row in referrals_rows[1:]:
            if row and str(row[0]) == str(telegram_id):
                try:
                    total_earnings += float(row[3]) if len(row) > 3 else 0
                except:
                    pass
        
        # ساخت پیام
        month_name = now.strftime("%B %Y")
        
        report = (
            f"📊 <b>گزارش ماهانه - {month_name}</b>\n\n"
            f"👤 <b>{username}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>این ماه:</b>\n"
            f"👥 معرفی‌ها: <b>{monthly_referrals}</b> نفر\n"
            f"💰 درآمد: <b>${monthly_earnings:.2f}</b>\n\n"
            f"📊 <b>کل:</b>\n"
            f"👥 کل معرفی‌ها: <b>{total_referrals}</b> نفر\n"
            f"💵 کل درآمد: <b>${total_earnings:.2f}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        # پیام انگیزشی بر اساس عملکرد
        if monthly_referrals == 0:
            report += "💡 این ماه هیچ معرفی نداشتید!\n🎯 با دعوت دوستان درآمد کسب کنید."
        elif monthly_referrals < 3:
            report += f"👍 عملکرد خوب!\n🚀 با {3 - monthly_referrals} معرفی دیگه به هدف ماهانه برسید."
        else:
            report += f"🔥 عالی! {monthly_referrals} معرفی در این ماه!\n🌟 به همین روال ادامه دهید."
        
        return report
        
    except Exception as e:
        logger.exception(f"Error generating monthly report: {e}")
        return None


async def send_monthly_reports():
    """Send monthly reports to all active users"""
    while True:
        try:
            # محاسبه زمان تا اول ماه آینده
            now = datetime.utcnow()
            next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=10, minute=0, second=0, microsecond=0)
            delay = (next_month - now).total_seconds()
            
            logger.info(f"📅 Next monthly report in {delay/3600/24:.1f} days")
            await asyncio.sleep(delay)
            
            # ارسال گزارش به همه کاربران فعال
            users_rows = await get_all_rows("Users")
            sent = 0
            failed = 0
            
            for row in users_rows[1:]:
                if not row or len(row) < 8:
                    continue
                
                telegram_id = int(row[0])
                status = row[7] if len(row) > 7 else ""
                
                # فقط برای کاربران فعال
                if status != "active":
                    continue
                
                try:
                    report = await generate_monthly_report(telegram_id)
                    if report:
                        await bot.send_message(
                            telegram_id,
                            report,
                            parse_mode="HTML",
                            reply_markup=main_menu_keyboard()
                        )
                        sent += 1
                        await asyncio.sleep(0.1)  # جلوگیری از spam
                except Exception as e:
                    logger.error(f"Failed to send report to {telegram_id}: {e}")
                    failed += 1
            
            logger.info(f"✅ Monthly reports sent: {sent}, failed: {failed}")
            
        except Exception as e:
            logger.exception(f"Error in monthly reports: {e}")
            await asyncio.sleep(3600)  # retry after 1 hour


async def create_discount_code(code: str, discount_percent: int, max_uses: int, valid_days: int, created_by: int) -> bool:
    """Create a new discount code"""
    try:
        # چک کد تکراری
        rows = await get_all_rows("DiscountCodes")
        for row in rows[1:]:
            if row and row[0].upper() == code.upper():
                return False  # کد تکراری
        
        valid_until = (datetime.utcnow() + timedelta(days=valid_days)).replace(microsecond=0).isoformat()
        
        await append_row("DiscountCodes", [
            code.upper(),
            str(discount_percent),
            str(max_uses),
            "0",  # used_count
            valid_until,
            str(created_by),
            now_iso(),
            "active"
        ])
        
        logger.info(f"✅ Discount code created: {code}")
        return True
        
    except Exception as e:
        logger.exception(f"Error creating discount code: {e}")
        return False


async def validate_discount_code(code: str) -> Optional[Tuple[int, int]]:
    """
    Validate discount code and return (discount_percent, row_index) or None
    """
    try:
        rows = await get_all_rows("DiscountCodes")
        now = datetime.utcnow()
        
        for idx, row in enumerate(rows[1:], start=2):
            if not row or len(row) < 8:
                continue
            
            if row[0].upper() != code.upper():
                continue
            
            # چک وضعیت
            status = row[7] if len(row) > 7 else ""
            if status != "active":
                return None
            
            # چک تاریخ انقضا
            valid_until = parse_iso(row[4]) if len(row) > 4 else None
            if valid_until and valid_until < now:
                return None
            
            # چک تعداد استفاده
            max_uses = int(row[2]) if len(row) > 2 and row[2] else 0
            used_count = int(row[3]) if len(row) > 3 and row[3] else 0
            
            if max_uses > 0 and used_count >= max_uses:
                return None
            
            # برگرداندن درصد تخفیف و ایندکس
            discount = int(row[1]) if len(row) > 1 else 0
            return (discount, idx)
        
        return None
        
    except Exception as e:
        logger.exception(f"Error validating code: {e}")
        return None


async def use_discount_code(code: str) -> bool:
    """Mark discount code as used (increment counter)"""
    try:
        rows = await get_all_rows("DiscountCodes")
        
        for idx, row in enumerate(rows[1:], start=2):
            if not row or row[0].upper() != code.upper():
                continue
            
            # افزایش شمارنده
            used_count = int(row[3]) if len(row) > 3 and row[3] else 0
            row[3] = str(used_count + 1)
            
            await update_row("DiscountCodes", idx, row)
            logger.info(f"✅ Discount code used: {code} ({used_count + 1} times)")
            return True
        
        return False
        
    except Exception as e:
        logger.exception(f"Error using discount code: {e}")
        return False


def generate_gift_code() -> str:
    """Generate unique gift card code"""
    return f"GIFT{uuid.uuid4().hex[:8].upper()}"


async def create_gift_card(product: str, buyer_id: int, buyer_username: str, message: str = "") -> Optional[str]:
    """Create a new gift card"""
    try:
        gift_code = generate_gift_code()
        amount_usd = NORMAL_PRICE if product == "normal" else PREMIUM_PRICE
        
        await append_row("GiftCards", [
            gift_code,
            product,
            str(amount_usd),
            str(buyer_id),
            buyer_username,
            "",  # recipient_id
            "",  # recipient_username
            message,
            "pending",
            now_iso(),
            ""   # redeemed_at
        ])
        
        logger.info(f"✅ Gift card created: {gift_code} by {buyer_id}")
        return gift_code
        
    except Exception as e:
        logger.exception(f"Error creating gift card: {e}")
        return None


async def redeem_gift_card(gift_code: str, recipient_id: int, recipient_username: str) -> Optional[Tuple[str, str, str]]:
    """
    Redeem gift card
    Returns: (product, message, buyer_username) or None
    """
    try:
        rows = await get_all_rows("GiftCards")
        
        for idx, row in enumerate(rows[1:], start=2):
            if not row or len(row) < 11:
                continue
            
            if row[0] != gift_code:
                continue
            
            # چک وضعیت
            status = row[8] if len(row) > 8 else ""
            if status != "pending":
                return None  # قبلاً استفاده شده
            
            # بررسی خریدار = گیرنده نباشه
            buyer_id = int(row[3]) if len(row) > 3 and row[3] else 0
            if buyer_id == recipient_id:
                return None  # نمیشه خودت استفاده کنی!
            
            # دریافت اطلاعات
            product = row[1] if len(row) > 1 else ""
            message = row[7] if len(row) > 7 else ""
            buyer_username = row[4] if len(row) > 4 else "کاربر"
            
            # آپدیت وضعیت
            row[6] = recipient_username
            row[5] = str(recipient_id)
            row[8] = "redeemed"
            row[10] = now_iso()
            
            await update_row("GiftCards", idx, row)

            # ✅ مورد ۲: اضافه گیرنده به عنوان معرف سطح ۱ خریدار
            try:
                # پیدا کردن یا ساخت یوزر گیرنده
                recipient_result = await find_user(recipient_id)
    
                if recipient_result:
                    recipient_row_idx, recipient_row = recipient_result
        
                    # اگه قبلاً کسی معرفش نکرده
                    if not recipient_row[5]:  # referred_by خالی باشه
                        recipient_row[5] = str(buyer_id)  # خریدار رو به عنوان معرف ست کن
                        await update_row("Users", recipient_row_idx, recipient_row)
                        logger.info(f"✅ Set {buyer_id} as referrer for gift recipient {recipient_id}")
    
            except Exception as e:
                logger.exception(f"Failed to set referrer for gift: {e}")

            logger.info(f"✅ Gift card redeemed: {gift_code} by {recipient_id}")
            return (product, message, buyer_username)
        
        return None
        
    except Exception as e:
        logger.exception(f"Error redeeming gift card: {e}")
        return None

async def create_boost_code(code: str, level1_percent: int, level2_percent: int, max_uses: int, valid_days: int, created_by: int) -> bool:
    """Create a new boost code (secret commission boost)"""
    try:
        # چک کد تکراری
        rows = await get_all_rows("BoostCodes")
        for row in rows[1:]:
            if row and row[0].upper() == code.upper():
                return False
        
        valid_until = (datetime.utcnow() + timedelta(days=valid_days)).replace(microsecond=0).isoformat()
        
        await append_row("BoostCodes", [
            code.upper(),
            str(level1_percent),
            str(level2_percent),
            str(max_uses),
            "0",
            valid_until,
            str(created_by),
            now_iso(),
            "active"
        ])
        
        logger.info(f"✅ Boost code created: {code} | L1: {level1_percent}% | L2: {level2_percent}%")
        return True
        
    except Exception as e:
        logger.exception(f"Error creating boost code: {e}")
        return False


async def validate_and_apply_boost(code: str, telegram_id: int) -> Optional[Dict[str, Any]]:
    """Validate boost code and apply to user"""
    try:
        rows = await get_all_rows("BoostCodes")
        now = datetime.utcnow()
        
        for idx, row in enumerate(rows[1:], start=2):
            if not row or len(row) < 9:
                continue
            
            if row[0].upper() != code.upper():
                continue
            
            # چک وضعیت
            status = row[8] if len(row) > 8 else ""
            if status != "active":
                return None
            
            # چک تاریخ انقضا
            valid_until = parse_iso(row[5]) if len(row) > 5 else None
            if valid_until and valid_until < now:
                return None
            
            # چک تعداد استفاده
            max_uses = int(row[3]) if len(row) > 3 and row[3] else 0
            used_count = int(row[4]) if len(row) > 4 and row[4] else 0
            if max_uses > 0 and used_count >= max_uses:
                return None
            
            # دریافت درصدها
            level1_percent = int(row[1]) if len(row) > 1 and row[1] else 8
            level2_percent = int(row[2]) if len(row) > 2 and row[2] else 12
            
            # چک اگه این کاربر قبلاً این کد رو فعال کرده
            users_rows = await get_all_rows("Users")
            for u_idx, u_row in enumerate(users_rows[1:], start=2):
                if u_row and str(u_row[0]) == str(telegram_id):
                    # نگه داشتن بوست در فیلد notes (فیلد ۱۰ به بعد)
                    # چک اگه قبلاً بوستی داره
                    if len(u_row) > 10 and u_row[10] and u_row[10].startswith("boost:"):
                        return {"error": "already_boosted"}
                    break
            
            # افزایش شمارنده استفاده
            row[4] = str(used_count + 1)
            await update_row("BoostCodes", idx, row)
            
            # ذخیره بوست در فیلد اضافی کاربر
            for u_idx, u_row in enumerate(users_rows[1:], start=2):
                if u_row and str(u_row[0]) == str(telegram_id):
                    # اضافه فیلد بوست
                    while len(u_row) < 11:
                        u_row.append("")
                    u_row[10] = f"boost:{code}:{level1_percent}:{level2_percent}"
                    await update_row("Users", u_idx, u_row)
                    break
            
            logger.info(f"✅ Boost applied: {code} to user {telegram_id} | L1: {level1_percent}% | L2: {level2_percent}%")
            
            return {
                "code": code,
                "level1_percent": level1_percent,
                "level2_percent": level2_percent
            }
        
        return None
        
    except Exception as e:
        logger.exception(f"Error applying boost: {e}")
        return None


async def get_user_boost(telegram_id: int) -> Optional[Dict[str, int]]:
    """Get user's active boost rates"""
    try:
        result = await find_user(telegram_id)
        if not result:
            return None
        
        _, row = result
        
        # چک فیلد بوست (فیلد ۱۰)
        if len(row) > 10 and row[10] and row[10].startswith("boost:"):
            parts = row[10].split(":")
            # فرمت: boost:CODE:L1_PERCENT:L2_PERCENT
            if len(parts) >= 4:
                return {
                    "code": parts[1],
                    "level1": int(parts[2]),
                    "level2": int(parts[3])
                }
        
        return None
        
    except Exception as e:
        logger.exception(f"Error getting user boost: {e}")
        return None

async def check_and_grant_auto_boost(telegram_id: int):
    """
    چک و اعطای بوست خودکار ۱۰ رفرال
    این بوست مستقل از بوست دستی ادمین هست
    """
    try:
        # ✅ چک اگه قبلاً بوست اتومات گرفته
        result = await find_user(telegram_id)
        if not result:
            return
        
        _, user_row = result
        boost_data = user_row[10] if len(user_row) > 10 else ""
        
        # اگه بوست با AUTO10_ داره = قبلاً گرفته
        if boost_data and "AUTO10_" in boost_data:
            return
        
        # شمارش رفرال‌های سطح ۱
        referrals_rows = await get_all_rows("Referrals")
        direct_referrals = 0
        
        for row in referrals_rows[1:]:
            if not row or len(row) < 3:
                continue
            if str(row[0]) == str(telegram_id) and row[2] == "1":
                direct_referrals += 1
        
        if direct_referrals < 10:
            return
        
        logger.info(f"🎉 User {telegram_id} reached 10 referrals!")
        
        boost_code = f"AUTO10_{telegram_id}_{int(time.time())}"
        level1_percent = 10
        level2_percent = 15
        
        # ساخت کد
        success = await create_boost_code(
            code=boost_code,
            level1_percent=level1_percent,
            level2_percent=level2_percent,
            max_uses=1,
            valid_days=36500,
            created_by=0
        )
        
        if not success:
            return
        
        # ✅ ثبت در Users
        users_rows = await get_all_rows("Users")
        for u_idx, u_row in enumerate(users_rows[1:], start=2):
            if u_row and str(u_row[0]) == str(telegram_id):
                current_boost = u_row[10] if len(u_row) > 10 else ""
                
                # اگه بوست دستی داره (شروع با boost: ولی نه AUTO)
                if current_boost and current_boost.startswith("boost:") and "AUTO10_" not in current_boost:
                    # بوست دستی داره - note کن
                    u_row[10] = current_boost + f"|auto:{boost_code}"
                else:
                    # بوست نداره - بوست اتومات بذار
                    while len(u_row) < 11:
                        u_row.append("")
                    u_row[10] = f"boost:{boost_code}:{level1_percent}:{level2_percent}"
                
                await update_row("Users", u_idx, u_row)
                
                # Mark used
                boost_rows = await get_all_rows("BoostCodes")
                for b_idx, b_row in enumerate(boost_rows[1:], start=2):
                    if b_row and b_row[0] == boost_code:
                        b_row[4] = "1"
                        await update_row("BoostCodes", b_idx, b_row)
                        break
                break
        
        # پیام به کاربر
        try:
            await bot.send_message(
                telegram_id,
                f"🎉 <b>تبریک! پاداش ۱۰ معرفی!</b>\n\n"
                f"✨ به <b>۱۰ معرفی مستقیم</b> رسیدید!\n\n"
                f"🎁 نرخ جدید:\n"
                f"📊 سطح ۱: <b>{level1_percent}%</b>\n"
                f"📊 سطح ۲: <b>{level2_percent}%</b>\n\n"
                f"💎 تمام پورسانت‌ها با نرخ جدید!",
                parse_mode="HTML"
            )
        except:
            pass
        
        # نوتیف ادمین
        if ADMIN_TELEGRAM_ID:
            try:
                await bot.send_message(
                    int(ADMIN_TELEGRAM_ID),
                    f"🎉 <b>بوست خودکار!</b>\n\n"
                    f"🆔 <code>{telegram_id}</code>\n"
                    f"👥 {direct_referrals} معرفی\n"
                    f"🎟 <code>{boost_code}</code>",
                    parse_mode="HTML"
                )
            except:
                pass
        
    except Exception as e:
        logger.exception(f"Auto-boost error: {e}")


# 



async def calculate_dashboard_stats() -> Dict[str, Any]:
    """Calculate comprehensive dashboard statistics"""
    try:
        stats = {}
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        
        # ============ Users Stats ============
        users_rows = await get_all_rows("Users")
        total_users = len(users_rows) - 1  # منهای header
        
        users_today = 0
        users_week = 0
        
        for row in users_rows[1:]:
            if not row or len(row) < 9:
                continue
            
            created = parse_iso(row[8]) if len(row) > 8 else None
            if created:
                if created >= today_start:
                    users_today += 1
                if created >= week_start:
                    users_week += 1
        
        stats['users'] = {
            'total': total_users,
            'today': users_today,
            'week': users_week
        }
        
        # ============ Subscriptions Stats ============
        subs_rows = await get_all_rows("Subscriptions")
        active_subs = 0
        expired_subs = 0
        normal_subs = 0
        premium_subs = 0
        
        for row in subs_rows[1:]:
            if not row or len(row) < 6:
                continue
            
            status = row[3] if len(row) > 3 else ""
            product = row[2] if len(row) > 2 else ""
            
            if status == "active":
                active_subs += 1
                if product == "premium":
                    premium_subs += 1
                else:
                    normal_subs += 1
            elif status == "expired":
                expired_subs += 1
        
        stats['subscriptions'] = {
            'active': active_subs,
            'expired': expired_subs,
            'normal': normal_subs,
            'premium': premium_subs
        }
        
        # ============ Revenue Stats ============
        purchases_rows = await get_all_rows("Purchases")
        total_revenue = 0.0
        revenue_today = 0.0
        revenue_week = 0.0
        approved_count = 0
        pending_count = 0
        rejected_count = 0
        
        daily_revenue = {}  # برای پیدا کردن بهترین روز
        hourly_revenue = {}  # برای پیدا کردن بهترین ساعت
        
        for row in purchases_rows[1:]:
            if not row or len(row) < 11:
                continue
            
            status = row[8] if len(row) > 8 else ""
            amount = float(row[4]) if len(row) > 4 and row[4] else 0
            
            if status == "approved":
                approved_count += 1
                total_revenue += amount
                
                # تاریخ تایید
                approved_at = parse_iso(row[10]) if len(row) > 10 else None
                if approved_at:
                    if approved_at >= today_start:
                        revenue_today += amount
                    if approved_at >= week_start:
                        revenue_week += amount
                    
                    # آمار روزانه
                    day_name = approved_at.strftime("%A")  # Monday, Tuesday, ...
                    daily_revenue[day_name] = daily_revenue.get(day_name, 0) + amount
                    
                    # آمار ساعتی
                    hour = approved_at.hour
                    hourly_revenue[hour] = hourly_revenue.get(hour, 0) + amount
            
            elif status == "pending":
                pending_count += 1
            elif status == "rejected":
                rejected_count += 1
        
        avg_purchase = total_revenue / approved_count if approved_count > 0 else 0
        
        # بهترین روز
        best_day = max(daily_revenue.items(), key=lambda x: x[1])[0] if daily_revenue else "N/A"
        
        # بهترین ساعت
        if hourly_revenue:
            best_hour = max(hourly_revenue.items(), key=lambda x: x[1])[0]
            best_hour_range = f"{best_hour:02d}:00-{(best_hour+1):02d}:00"
        else:
            best_hour_range = "N/A"
        
        stats['revenue'] = {
            'total': total_revenue,
            'today': revenue_today,
            'week': revenue_week,
            'avg_purchase': avg_purchase,
            'approved': approved_count,
            'pending': pending_count,
            'rejected': rejected_count,
            'best_day': best_day,
            'best_hour': best_hour_range
        }
        
        # ============ Conversion Rates ============
        # تست → خرید
        test_purchases = sum(1 for row in purchases_rows[1:] if row and len(row) > 3 and row[3] == "test")
        test_to_purchase_rate = (approved_count / test_purchases * 100) if test_purchases > 0 else 0
        
        # معمولی → ویژه
        normal_to_premium_rate = (premium_subs / (normal_subs + premium_subs) * 100) if (normal_subs + premium_subs) > 0 else 0
        
        stats['conversion'] = {
            'test_to_purchase': test_to_purchase_rate,
            'normal_to_premium': normal_to_premium_rate
        }
        
        # ============ Referrals Stats ============
        referrals_rows = await get_all_rows("Referrals")
        total_commissions = 0.0
        
        for row in referrals_rows[1:]:
            if row and len(row) > 3:
                try:
                    total_commissions += float(row[3])
                except:
                    pass
        
        stats['referrals'] = {
            'total_count': len(referrals_rows) - 1,
            'total_commissions': total_commissions
        }
        
        # ============ Withdrawals Stats ============
        withdrawals_rows = await get_all_rows("Withdrawals")
        total_withdrawn = 0.0
        pending_withdrawals = 0
        
        for row in withdrawals_rows[1:]:
            if not row or len(row) < 7:
                continue
            
            status = row[6] if len(row) > 6 else ""
            amount = float(row[2]) if len(row) > 2 and row[2] else 0
            
            if status == "completed":
                total_withdrawn += amount
            elif status == "pending":
                pending_withdrawals += 1
        
        stats['withdrawals'] = {
            'total': total_withdrawn,
            'pending': pending_withdrawals
        }
        
        return stats
        
    except Exception as e:
        logger.exception(f"Error calculating dashboard stats: {e}")
        return {}




# ============================================
# COMMAND HANDLERS
# ============================================
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    """Start command"""
    user = message.from_user
    args = message.get_args()

    # چک اگر لینک هدیه است
    if args and args.startswith("gift_"):
        gift_code = args.replace("gift_", "")
    
        # Redeem gift
        result = await redeem_gift_card(gift_code, user.id, user.username or "")
    
        if result:
            product, gift_message, buyer_username = result
        
            # فعال‌سازی اشتراک
            await activate_subscription(user.id, user.username or "", product, "gift")
        
            # پیام به گیرنده
            await message.reply(
                f"🎊 <b>تبریک! هدیه دریافت شد!</b>\n\n"
                f"🎁 از طرف: @{buyer_username}\n"
                f"💎 اشتراک: {'ویژه' if product == 'premium' else 'معمولی'}\n"
                f"{'💬 پیام: ' + gift_message if gift_message else ''}\n\n"
                f"✅ اشتراک شما فعال شد!\n"
                f"📅 مدت: ۶ ماه",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard()
            )
        
            # پیام به خریدار
            buyer_id = None
            rows = await get_all_rows("GiftCards")
            for row in rows[1:]:
                if row and row[0] == gift_code:
                    buyer_id = int(row[3]) if len(row) > 3 and row[3] else None
                    break
        
            if buyer_id:
                try:
                    await bot.send_message(
                        buyer_id,
                        f"🎉 <b>هدیه شما دریافت شد!</b>\n\n"
                        f"👤 توسط: @{user.username or user.full_name}\n"
                        f"⏰ در: {datetime.utcnow().strftime('%Y/%m/%d %H:%M')}",
                        parse_mode="HTML"
                    )
                except:
                    pass
        
            return
        else:
            await message.reply(
                "❌ <b>کد هدیه نامعتبر!</b>\n\n"
                "این کد قبلاً استفاده شده یا اشتباه است.",
                parse_mode="HTML"
            )
            return

    # ✅ فیکس #2: چک عضویت کانال فقط اگه لینک هدیه نیست
    # (برای لینک هدیه چک عضویت نمیخواد چون هنوز ثبت‌نام نکرده)
    if not (args and args.startswith("gift_")):
        # ✅ اول از همه چک عضویت کانال
        is_member, missing = await check_required_channels(user.id)
        
        if not is_member:
            kb = channel_membership_keyboard(missing)
            await send_and_record(
                user.id,
                "🔐 <b>برای استفاده از ربات ابتدا باید در کانال‌های زیر عضو شوید:</b>\n\n"
                "پس از عضویت روی <b>✅ بررسی عضویت</b> کلیک کنید.",
                parse_mode="HTML",
                reply_markup=kb
            )
            return
    
    # ✅ چک کردن یوزر در دیتابیس
    result = await find_user(user.id)
    
    if result:
        row_idx, row = result
        email = row[3] if len(row) > 3 else ""
        
        # اگر ایمیل نداره، بگیر
        if not email:
            user_states[user.id] = {"state": "awaiting_email", "attempt": 1}
            await send_and_record(
                user.id,
                "📧 <b>لطفاً ایمیل خود را وارد کنید:</b>\n\n"
                "مثال: <code>example@gmail.com</code>",
                parse_mode="HTML"
            )
            return
    else:
        # ✅ یوزر جدیده - ثبت کن
        referred_by = ""
        # ✅ فیکس #1: لینک هدیه رو به عنوان رفرال حساب نکن
        if args and not args.startswith("gift_"):
            rows = await get_all_rows("Users")
            for r in rows[1:]:
                if len(r) > 4 and r[4].upper() == args.upper():
                    referred_by = r[0]
                    break
        
        new_row = [
            str(user.id),
            user.username or "",
            user.full_name or "",
            "",  # ایمیل خالی
            generate_referral_code(),
            referred_by,
            "0",
            "active",
            now_iso(),
            now_iso(),
            ""  # ✅ فیکس #1: فیلد ۱۱ boost_data
        ]
        
        await append_row("Users", new_row)
        
        # درخواست ایمیل
        user_states[user.id] = {"state": "awaiting_email", "attempt": 1}
        await send_and_record(
            user.id,
            "👋 <b>خوش آمدید!</b>\n\n"
            "📧 لطفاً ایمیل خود را وارد کنید:\n\n"
            "مثال: <code>example@gmail.com</code>",
            parse_mode="HTML"
        )
        return  # ✅ فیکس #1: این return ضروریه!

    # ✅ تشخیص ادمین و تعیین منو و پیام
    if is_admin(user.id):
        menu_kb = admin_menu_keyboard()
        greeting = f"👋 <b>سلام {user.full_name}!</b>\n\n🔐 <b>پنل ادمین</b>"
    else:
        menu_kb = main_menu_keyboard()
        greeting = f"👋 <b>سلام {user.full_name}!</b>"
    
    # ✅ نمایش منوی اصلی
    subscription = await get_active_subscription(user.id)
    
    if subscription:
        expires = parse_iso(subscription[5])
        expires_str = expires.strftime("%Y/%m/%d") if expires else "نامشخص"
        sub_type = subscription[2] if len(subscription) > 2 else "unknown"
        sub_name = "ویژه 💎" if sub_type == "premium" else "معمولی ⭐️"
        
        await send_and_record(
            user.id,
            f"{greeting}\n\n"
            f"✅ اشتراک: {sub_name}\n"
            f"📅 انقضا: <code>{expires_str}</code>\n\n"
            f"از منوی زیر استفاده کنید:",
            parse_mode="HTML",
            reply_markup=menu_kb
        )
    else:
        # فیکس: پیام رو قبل از f-string بساز (جلوگیری از syntax error)
        if is_admin(user.id):
            status_msg = "از منوی مدیریت استفاده کنید:"
        else:
            status_msg = "شما اشتراک فعالی ندارید.\n\n🆓 تست رایگان یا 💎 خرید اشتراک"
        
        await send_and_record(
            user.id,
            f"{greeting}\n\n{status_msg}",
            parse_mode="HTML",
            reply_markup=menu_kb
        )


@dp.message_handler(commands=["amiadmin"])
async def cmd_am_i_admin(message: types.Message):
    """تست ادمین بودن"""
    user_id = message.from_user.id
    
    admin1 = os.getenv("ADMIN_TELEGRAM_ID")
    admin2 = os.getenv("ADMIN2_TELEGRAM_ID")
    
    result = is_admin(user_id)
    
    await message.reply(
        f"🆔 <b>ID شما:</b> <code>{user_id}</code>\n\n"
        f"👤 <b>ادمین اصلی:</b> <code>{admin1}</code>\n"
        f"👤 <b>ادمین دوم:</b> <code>{admin2 or 'تنظیم نشده'}</code>\n\n"
        f"{'✅ شما ادمین هستید!' if result else '❌ شما ادمین نیستید!'}",
        parse_mode="HTML"
    )


# 

@dp.callback_query_handler(lambda c: c.data == "check_membership")
async def callback_check_membership(callback: types.CallbackQuery):
    """Check membership"""
    user = callback.from_user
    is_member, missing = await check_required_channels(user.id)
    
    if is_member:
        await callback.answer("✅ عضویت تایید شد!", show_alert=True)
        await create_or_update_user(user)
        
        await callback.message.edit_text(
            "✅ <b>عضویت شما تایید شد!</b>\n\n"
            "اکنون می‌توانید از ربات استفاده کنید.",
            parse_mode="HTML"
        )
        
        await bot.send_message(
            user.id,
            "از منوی زیر استفاده کنید:",
            reply_markup=main_menu_keyboard()
        )
    else:
        await callback.answer("❌ هنوز عضو نشده‌اید!", show_alert=True)
        kb = channel_membership_keyboard(missing)
        await callback.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "close_share")
async def callback_close_share(callback: types.CallbackQuery):
    """Close share window"""
    try:
        await callback.message.delete()
    except:
        pass
    
    await bot.send_message(
        callback.from_user.id,
        "از منوی زیر استفاده کنید:",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


# ============================================
# EMAIL HANDLERS
# ============================================
@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_email")
async def handle_email_input(message: types.Message):
    """Handle email input"""
    user = message.from_user
    email = message.text.strip().lower()
    state = user_states.get(user.id, {})
    attempt = state.get("attempt", 1)
    
    if not is_valid_email(email):
        await message.reply(
            "❌ ایمیل نامعتبر!\n\n"
            "مثال صحیح: <code>example@gmail.com</code>",
            parse_mode="HTML"
        )
        return
    
    if attempt == 1:
        user_states[user.id] = {
            "state": "awaiting_email_confirm",
            "email": email,
            "attempt": 2
        }
        
        await message.reply(
            f"📧 ایمیل: <code>{email}</code>\n\n"
            "⚠️ برای تایید دوباره وارد کنید:",
            parse_mode="HTML"
        )

@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_email_confirm")
async def handle_email_confirmation(message: types.Message):
    """Handle email confirmation"""
    user = message.from_user
    email_confirm = message.text.strip().lower()
    state = user_states.get(user.id, {})
    original_email = state.get("email", "")
    
    if email_confirm != original_email:
        user_states[user.id] = {"state": "awaiting_email", "attempt": 1}
        await message.reply(
            "❌ <b>ایمیل‌ها مطابقت ندارند!</b>\n\n"
            "دوباره وارد کنید:",
            parse_mode="HTML"
        )
        return
    
    result = await find_user(user.id)
    if result:
        row_idx, row = result
        row[3] = original_email
        await update_row("Users", row_idx, row)
    else:
        await create_or_update_user(user, email=original_email)
    
    user_states.pop(user.id, None)
    
    await message.reply("✅ <b>ایمیل ثبت شد!</b>", parse_mode="HTML")
    await send_and_record(user.id, "از منوی زیر استفاده کنید:", reply_markup=main_menu_keyboard())

# ============================================
# MENU HANDLERS
# ============================================
@dp.message_handler(lambda msg: msg.text == "🆓 تست کانال")
async def handle_test_channel(message: types.Message):
    """Test channel handler"""
    user = message.from_user
    
    # ✅ چک عضویت
    if not await check_membership_for_all_messages(message):
        return

    # ✅ چک رزرو
    if not await check_reserve_block(message):
        return
    
    if not TEST_CHANNEL_ID:
        await message.reply("❌ کانال تست در دسترس نیست.")
        return
    
    rows = await get_all_rows("Purchases")
    for row in rows[1:]:
        if row and str(row[1]) == str(user.id) and row[3] == "test":
            await message.reply("⚠️ شما قبلاً از تست استفاده کرده‌اید.")
            return
    
    link = await create_invite_link(TEST_CHANNEL_ID, expire_minutes=5)
    
    if not link:
        await message.reply("❌ خطا در ایجاد لینک.")
        return
    
    purchase_id = generate_purchase_id()
    await append_row("Purchases", [
        purchase_id, str(user.id), user.username or "",
        "test", "0", "0", "test", "test",
        "approved", now_iso(), now_iso(), "system", "5min test"
    ])
    
    await message.reply(
        "🎉 <b>لینک تست (۵ دقیقه):</b>\n\n"
        f"{link}\n\n"
        "⏰ بعد از ۵ دقیقه حذف می‌شوید.",
        parse_mode="HTML"
    )
    
    asyncio.create_task(schedule_test_removal(user.id, TEST_CHANNEL_ID))

async def schedule_test_removal(user_id: int, channel_id: str):
    """Schedule test removal"""
    try:
        await asyncio.sleep(300)
        await remove_from_channel(channel_id, user_id)
        try:
            await bot.send_message(
                user_id,
                "⏰ تست به پایان رسید.",
                reply_markup=main_menu_keyboard()
            )
        except:
            pass
    except Exception as e:
        logger.exception(f"Test removal error: {e}")

@dp.message_handler(lambda msg: msg.text == "💎 خرید اشتراک")
async def handle_buy_subscription(message: types.Message):
    """Buy subscription"""
    
    # ✅ چک عضویت
    if not await check_membership_for_all_messages(message):
        return
      
    # ✅ چک رزرو
    if not await check_reserve_block(message):
        return

    kb = subscription_keyboard()
    await send_and_record(
        message.from_user.id,
        "💎 <b>خرید اشتراک</b>\n\n"
        f"⭐️ معمولی: <b>${NORMAL_PRICE}</b>\n"
        f"   • کانال معمولی\n"
        f"   • ۶ ماه\n\n"
        f"💎 ویژه: <b>${PREMIUM_PRICE}</b>\n"
        f"   • هر دو کانال\n"
        f"   • ۶ ماه\n\n"
        f"یک گزینه انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query_handler(lambda c: c.data in ["buy_normal", "buy_premium"])
async def callback_buy(callback: types.CallbackQuery):
    """Buy callback"""
    product = "normal" if callback.data == "buy_normal" else "premium"
    price = NORMAL_PRICE if product == "normal" else PREMIUM_PRICE
    
    kb = payment_method_keyboard(product)
    
    await callback.message.edit_text(
        f"💳 <b>پرداخت {'معمولی' if product == 'normal' else 'ویژه'}</b>\n\n"
        f"💰 مبلغ: <b>${price}</b>\n\n"
        f"روش پرداخت را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "buy_reserve")
async def callback_buy_reserve(callback: types.CallbackQuery):
    """شروع پیش‌پرداخت"""
    user = callback.from_user
    
    # چک اگه قبلاً رزرو داره
    reserve = await get_user_reserve_status(user.id)
    if reserve["has_reserve"]:
        product_name = "ویژه" if reserve["product"] == "premium" else "معمولی"
        paid = reserve["amount_paid"]
        total = PREMIUM_PRICE if reserve["product"] == "premium" else NORMAL_PRICE
        remaining = total - paid
        
        await callback.message.edit_text(
            f"⚠️ <b>شما قبلاً رزرو کرده‌اید!</b>\n\n"
            f"📦 محصول: {product_name}\n"
            f"💵 پرداخت شده: ${paid:.2f}\n"
            f"💰 باقیمانده: ${remaining:.2f}\n\n"
            f"لطفاً ابتدا رزرو قبلی را تکمیل کنید.",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # انتخاب محصول
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            f"⭐️ رزرو معمولی (${NORMAL_PRICE}) - پیش‌پرداخت $2",
            callback_data="reserve_normal"
        ),
        InlineKeyboardButton(
            f"💎 رزرو ویژه (${PREMIUM_PRICE}) - پیش‌پرداخت $2",
            callback_data="reserve_premium"
        ),
        InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_buy")
    )
    
    await callback.message.edit_text(
        f"💵 <b>پیش‌پرداخت و رزرو</b>\n\n"
        f"با پرداخت <b>$2</b>، جایگاه خود را رزرو کنید!\n\n"
        f"📋 <b>مزایا:</b>\n"
        f"• جایگاه شما تا تکمیل پرداخت محفوظ است\n"
        f"• بدون محدودیت زمانی\n"
        f"• تکمیل در هر زمان\n\n"
        f"⚠️ <b>توجه:</b>\n"
        f"تا تکمیل پرداخت، امکانات ربات غیرفعال می‌شوند.\n\n"
        f"محصول مورد نظر را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("reserve_"))
async def callback_reserve_product(callback: types.CallbackQuery):
    """انتخاب محصول برای رزرو"""
    user = callback.from_user
    product = callback.data.replace("reserve_", "")  # normal or premium
    
    # روش پرداخت
    kb = payment_method_keyboard(f"reserve_{product}")
    
    product_name = "ویژه" if product == "premium" else "معمولی"
    total_price = PREMIUM_PRICE if product == "premium" else NORMAL_PRICE
    
    await callback.message.edit_text(
        f"💳 <b>پیش‌پرداخت {product_name}</b>\n\n"
        f"💵 مبلغ پیش‌پرداخت: <b>$2</b>\n"
        f"💰 قیمت کل: <b>${total_price}</b>\n"
        f"📊 باقیمانده: <b>${total_price - 2}</b>\n\n"
        f"روش پرداخت را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "buy_gift")
async def callback_buy_gift(callback: types.CallbackQuery):
    """Buy gift card"""
    user = callback.from_user
    
    # ✅ مورد ۱: چک اینکه کاربر قبلاً خرید کرده باشه
    purchases_rows = await get_all_rows("Purchases")
    has_purchased = False
    
    for row in purchases_rows[1:]:
        if not row or len(row) < 10:
            continue
        
        # چک اگه این کاربر خرید تایید شده داره
        if str(row[1]) == str(user.id) and row[9] == "approved":
            # فقط خریدهای واقعی (نه هدیه) رو حساب کن
            product = row[3] if len(row) > 3 else ""
            if not product.startswith("gift_"):
                has_purchased = True
                break
    
    if not has_purchased:
        await callback.answer(
            "⚠️ برای خرید هدیه، ابتدا باید خودتان یک اشتراک خریداری کنید!",
            show_alert=True
        )
        return
    
    # ادامه کد عادی
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            f"🎁 هدیه معمولی - ${NORMAL_PRICE}",
            callback_data="gift_normal"
        ),
        InlineKeyboardButton(
            f"💎 هدیه ویژه - ${PREMIUM_PRICE}",
            callback_data="gift_premium"
        ),
        InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_buy")
    )
    
    await callback.message.edit_text(
        "🎁 <b>خرید هدیه</b>\n\n"
        "اشتراک را برای دوست خود هدیه بدهید!\n\n"
        f"⭐️ معمولی: <b>${NORMAL_PRICE}</b>\n"
        f"💎 ویژه: <b>${PREMIUM_PRICE}</b>\n\n"
        "نوع هدیه را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()



@dp.callback_query_handler(lambda c: c.data.startswith("gift_"))
async def callback_gift_type(callback: types.CallbackQuery):
    """Gift type selected"""
    user = callback.from_user
    product = callback.data.replace("gift_", "")  # normal or premium
    
    user_states[user.id] = {
        "state": "awaiting_gift_message",
        "gift_product": product
    }
    
    await callback.message.edit_text(
        "🎁 <b>پیام هدیه</b>\n\n"
        "یک پیام برای دریافت‌کننده بنویسید:\n\n"
        "مثال: <code>تولدت مبارک! 🎉</code>\n\n"
        "یا /skip برای رد کردن",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "enter_discount")
async def callback_enter_discount(callback: types.CallbackQuery):
    """Enter discount code"""
    user = callback.from_user
    
    user_states[user.id] = {"state": "awaiting_discount_code"}
    
    # ✅ مورد ۳: اضافه دکمه بازگشت
    kb_back = InlineKeyboardMarkup()
    kb_back.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_buy"))
    
    await callback.message.edit_text(
        "🎟 <b>کد تخفیف</b>\n\n"
        "لطفاً کد تخفیف خود را وارد کنید:\n\n"
        "مثال: <code>SUMMER20</code>",
        parse_mode="HTML",
        reply_markup=kb_back
    )
    await callback.answer()



@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_discount_code")
async def handle_discount_code_input(message: types.Message):
    """Handle discount code input"""
    user = message.from_user
    code = message.text.strip().upper()
    
    validation = await validate_discount_code(code)
    
    if validation:
        discount_percent, _ = validation
        user_states[user.id] = {
            "state": "discount_validated",
            "discount_code": code,
            "discount_percent": discount_percent
        }
        
        await message.reply(
            f"✅ <b>کد تخفیف معتبر!</b>\n\n"
            f"🎟 کد: <code>{code}</code>\n"
            f"💰 تخفیف: <b>{discount_percent}%</b>\n\n"
            f"حالا اشتراک مورد نظر را انتخاب کنید:",
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )
    else:
        user_states.pop(user.id, None)
        
        await message.reply(
            "❌ <b>کد تخفیف نامعتبر!</b>\n\n"
            "کد وارد شده منقضی شده یا اشتباه است.",
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )


@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_gift_message")
async def handle_gift_message(message: types.Message):
    """Handle gift message input"""
    user = message.from_user
    state = user_states.get(user.id, {})
    product = state.get("gift_product", "normal")
    
    gift_message = "" if message.text == "/skip" else message.text.strip()
    
    # انتخاب روش پرداخت
    price_usd = NORMAL_PRICE if product == "normal" else PREMIUM_PRICE
    
    user_states[user.id] = {
        "state": "awaiting_gift_payment",
        "gift_product": product,
        "gift_message": gift_message
    }
    
    kb = payment_method_keyboard(f"gift_{product}")
    
    await message.reply(
        f"💳 <b>پرداخت هدیه</b>\n\n"
        f"💰 مبلغ: <b>${price_usd}</b>\n"
        f"🎁 نوع: {'معمولی' if product == 'normal' else 'ویژه'}\n"
        f"💬 پیام: {gift_message if gift_message else '(بدون پیام)'}\n\n"
        "روش پرداخت را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )


# ============================================
# PART 2 COMPLETE - Continue to Part 3
# ============================================
"""
Telegram Subscription Bot - Part 3A
Payment Processing & Wallet System
"""

# ============================================
# PAYMENT PROCESSING
# ============================================
@dp.callback_query_handler(lambda c: c.data.startswith("pay_"))
async def callback_payment_method(callback: types.CallbackQuery):
    """Payment method selection - با پشتیبانی از پیش‌پرداخت"""
    user = callback.from_user

    parts = callback.data.split("_")
    method = parts[1]  # card یا usdt
    product = "_".join(parts[2:])  # normal, premium, gift_normal, reserve_normal, complete_normal, etc.

    # ─────────────────────────────────────────────────────────
    # تشخیص نوع خرید
    # ─────────────────────────────────────────────────────────
    is_gift = product.startswith("gift_")
    is_reserve = product.startswith("reserve_")  # ✅ جدید
    is_complete = product.startswith("complete_")  # ✅ جدید
    
    # استخراج محصول اصلی
    if is_gift:
        actual_product = product.replace("gift_", "")
        price_usd = NORMAL_PRICE if actual_product == "normal" else PREMIUM_PRICE
    elif is_reserve:
        # ✅ پیش‌پرداخت - همیشه $2
        actual_product = product.replace("reserve_", "")
        price_usd = 2.0
    elif is_complete:
        # ✅ تکمیل - محاسبه باقیمانده
        actual_product = product.replace("complete_", "")
        
        # دریافت اطلاعات رزرو
        reserve = await get_user_reserve_status(user.id)
        
        if not reserve["has_reserve"]:
            await callback.answer("❌ رزرو یافت نشد!", show_alert=True)
            return
        
        # محاسبه باقیمانده
        total_price = NORMAL_PRICE if actual_product == "normal" else PREMIUM_PRICE
        price_usd = total_price - reserve["amount_paid"]
    else:
        # خرید معمولی
        actual_product = product
        price_usd = NORMAL_PRICE if product == "normal" else PREMIUM_PRICE

    # چک کد تخفیف - فقط برای خرید عادی (نه هدیه، نه رزرو، نه تکمیل)
    discount_applied = 0
    if not is_gift and not is_reserve and not is_complete:
        if user.id in user_states and "discount_code" in user_states[user.id]:
            code = user_states[user.id]["discount_code"]
            validation = await validate_discount_code(code)

            if validation:
                discount_percent, _ = validation
                discount_applied = discount_percent
                price_usd = price_usd * (100 - discount_percent) / 100
                logger.info(f"✅ Discount applied: {code} ({discount_percent}%)")

    # ─────────────────────────────────────────────────────────
    # پرداخت کارت بانکی
    # ─────────────────────────────────────────────────────────
    if method == "card":
        usdt_rate = await get_usdt_price_irr()
        price_irr = price_usd * usdt_rate
        purchase_id = generate_purchase_id()
        
        await append_row("Purchases", [
            purchase_id, str(user.id), user.username or "", 
            product,  # ✅ محصول کامل: normal, gift_normal, reserve_normal, complete_normal
            str(price_usd), str(price_irr), "card", "", "pending",
            now_iso(), "", "", ""
        ])
        
        user_states[user.id] = {
            "state": "awaiting_card_receipt",
            "purchase_id": purchase_id,
            "product": product,  # ✅ محصول کامل
            "amount_usd": price_usd,
            "amount_irr": price_irr
        }
        
        support_username = os.getenv("SUPPORT_USERNAME", "@YourSupportAccount")
        
        # ✅ متن پیام بسته به نوع
        if is_reserve:
            product_text = f"پیش‌پرداخت {'ویژه' if actual_product == 'premium' else 'معمولی'}"
        elif is_complete:
            product_text = f"تکمیل {'ویژه' if actual_product == 'premium' else 'معمولی'}"
        elif is_gift:
            product_text = f"هدیه {'ویژه' if actual_product == 'premium' else 'معمولی'}"
        else:
            product_text = f"اشتراک {'ویژه' if product == 'premium' else 'معمولی'}"
        
        await callback.message.edit_text(
            f"💳 <b>پرداخت با کارت بانکی</b>\n\n"
            f"📦 محصول: {product_text}\n"
            f"💵 مبلغ: <b>{price_irr:,.0f}</b> تومان\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 <b>شماره کارت:</b>\n<code>{CARD_NUMBER}</code>\n\n"
            f"👤 <b>به نام:</b> {CARD_HOLDER}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ پس از واریز:\n"
            f"۱. عکس رسید را بگیرید\n"
            f"۲. به {support_username} ارسال کنید\n"
            f"۳. همراه عکس این شناسه را بفرستید:\n"
            f"<code>{purchase_id}</code>\n\n"
            f"⏰ پس از تایید، {'رزرو ثبت می‌شود' if is_reserve else 'اشتراک فعال می‌شود'}.",
            parse_mode="HTML"
        )
    
    # ─────────────────────────────────────────────────────────
    # پرداخت تتر
    # ─────────────────────────────────────────────────────────
    elif method == "usdt":
        purchase_id = generate_purchase_id()
        
        await append_row("Purchases", [
            purchase_id, str(user.id), user.username or "", product,
            str(price_usd), "0", "usdt", "", "pending",
            now_iso(), "", "", ""
        ])
        
        user_states[user.id] = {
            "state": "awaiting_usdt_txid",
            "purchase_id": purchase_id,
            "product": product,  # ✅ محصول کامل
            "amount_usd": price_usd
        }
        
        # ✅ متن پیام
        if is_reserve:
            product_text = f"پیش‌پرداخت {'ویژه' if actual_product == 'premium' else 'معمولی'}"
        elif is_complete:
            product_text = f"تکمیل {'ویژه' if actual_product == 'premium' else 'معمولی'}"
        elif is_gift:
            product_text = f"هدیه {'ویژه' if actual_product == 'premium' else 'معمولی'}"
        else:
            product_text = f"اشتراک {'ویژه' if product == 'premium' else 'معمولی'}"
        
        await callback.message.edit_text(
            f"🪙 <b>پرداخت با تتر (USDT)</b>\n\n"
            f"📦 محصول: {product_text}\n"
            f"💵 مبلغ: <b>${price_usd} USDT</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <b>شبکه:</b> BEP20 (BSC)\n\n"
            f"📋 <b>آدرس:</b>\n<code>{TETHER_WALLET}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ پس از واریز، TXID را ارسال کنید.\n\n"
            f"🔢 شناسه: <code>{purchase_id}</code>",
            parse_mode="HTML"
        )
    
    await callback.answer()

@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_card_receipt",
                   content_types=types.ContentType.PHOTO)
async def handle_card_receipt(message: types.Message):
    """Handle card receipt photo"""
    user = message.from_user
    state = user_states.get(user.id, {})
    purchase_id = state.get("purchase_id")
    product = state.get("product")
    amount_usd = state.get("amount_usd")
    amount_irr = state.get("amount_irr")
    
    if not purchase_id:
        await message.reply("❌ خطا: سفارش یافت نشد.")
        return
    
    # Save photo to purchases
    rows = await get_all_rows("Purchases")
    purchase_idx = None
    
    for idx, row in enumerate(rows[1:], start=2):
        if row and row[0] == purchase_id:
            purchase_idx = idx
            row[7] = f"photo:{message.photo[-1].file_id}"
            await update_row("Purchases", idx, row)
            break
    
    user_states.pop(user.id, None)
    
    await message.reply(
        "✅ <b>رسید دریافت شد!</b>\n\n"
        f"🔢 شناسه: <code>{purchase_id}</code>\n\n"
        "⏳ در حال بررسی توسط پشتیبان...",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )
    
    # Send to support with inline buttons
    if ADMIN_TELEGRAM_ID and purchase_idx:
        try:
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton("✅ تایید", callback_data=f"approve_card_{purchase_id}_{user.id}_{purchase_idx}"),
                InlineKeyboardButton("❌ رد", callback_data=f"reject_card_{purchase_id}_{user.id}_{purchase_idx}")
            )
            
            await bot.send_photo(
                int(ADMIN_TELEGRAM_ID),
                message.photo[-1].file_id,
                caption=f"💳 <b>رسید پرداخت جدید</b>\n\n"
                        f"👤 <b>کاربر:</b> {user.full_name}\n"
                        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                        f"📦 <b>محصول:</b> {'معمولی' if product == 'normal' else 'ویژه'}\n"
                        f"💰 <b>مبلغ:</b> ${amount_usd} (≈ {amount_irr:,.0f} تومان)\n\n"
                        f"🔢 <b>شناسه:</b> <code>{purchase_id}</code>",
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            logger.exception(f"Failed to notify admin: {e}")


@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_usdt_txid")
async def handle_usdt_txid(message: types.Message):
    """Handle USDT TXID"""
    user = message.from_user
    state = user_states.get(user.id, {})
    purchase_id = state.get("purchase_id")
    product = state.get("product")
    amount_usd = state.get("amount_usd")
    txid = message.text.strip()
    
    if not purchase_id:
        await message.reply("❌ سفارش یافت نشد.")
        return
    
    if len(txid) < 20:
        await message.reply("❌ TXID نامعتبر!")
        return
    
    rows = await get_all_rows("Purchases")
    for idx, row in enumerate(rows[1:], start=2):
        if row and row[0] == purchase_id:
            row[7] = txid
            row[8] = "pending"
            await update_row("Purchases", idx, row)
            break
    
    user_states.pop(user.id, None)
    
    await message.reply(
        f"✅ <b>TXID دریافت شد!</b>\n\n"
        f"🔢 <code>{purchase_id}</code>\n\n"
        f"⏳ در حال بررسی...",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )


    if ADMIN_TELEGRAM_ID:
        try:
            kb = admin_purchase_keyboard(purchase_id, user.id)
            await bot.send_message(
                int(ADMIN_TELEGRAM_ID),
                f"🔔 <b>سفارش جدید</b>\n\n"
                f"👤 {user.full_name}\n"
                f"🆔 <code>{user.id}</code>\n"
                f"📦 {product}\n"
                f"💰 ${amount_usd} USDT\n"
                f"🪙 تتر BEP20\n"
                f"🔗 <code>{txid}</code>\n"
                f"🔢 <code>{purchase_id}</code>",
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            logger.exception(f"Admin notify failed: {e}")

@dp.callback_query_handler(lambda c: c.data.startswith("approve_card_") or c.data.startswith("reject_card_"))
async def callback_admin_card_approval(callback: types.CallbackQuery):
    """Admin approve/reject from Telegram (card payment)"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ شما ادمین نیستید!", show_alert=True)
        return
    
    parts = callback.data.split("_")
    action = parts[0]  # approve or reject
    purchase_id = parts[2]
    user_id = int(parts[3])
    purchase_idx = int(parts[4])
    
    try:
        rows = await get_all_rows("Purchases")
        
        if purchase_idx < 2 or purchase_idx > len(rows):
            await callback.answer("❌ سفارش یافت نشد!", show_alert=True)
            return
        
        row = rows[purchase_idx - 1]
        
        # Get details
        product = row[3] if len(row) > 3 else ""
        amount_usd = float(row[4]) if len(row) > 4 and row[4] else 0
        payment_method = "card"
        username = row[2] if len(row) > 2 else ""
        
        if action == "approve":
            # Update sheet with admin_action
            header = rows[0]
            try:
                admin_action_idx = header.index("admin_action")
                row[admin_action_idx] = "approve"
                await update_row("Purchases", purchase_idx, row)
            except ValueError:
                # Fallback: update status directly
                try:
                    status_idx = header.index("status")
                    approved_at_idx = header.index("approved_at")
                    approved_by_idx = header.index("approved_by")
                    
                    row[status_idx] = "approved"
                    row[approved_at_idx] = now_iso()
                    row[approved_by_idx] = str(callback.from_user.id)
                    await update_row("Purchases", purchase_idx, row)
                except ValueError as e:
                    logger.error(f"Column not found: {e}")
                    await callback.answer("❌ خطای ساختار شیت!", show_alert=True)
                    return

                # Manually process
                await activate_subscription(user_id, username, product, payment_method)
                await process_referral_commission(purchase_id, user_id, amount_usd)
                
                result = await find_user(user_id)
                if result:
                    _, user_row = result
                    referral_code = user_row[4] if len(user_row) > 4 else ""
                    
                    await bot.send_message(
                        user_id,
                        f"🎉 <b>پرداخت تایید شد!</b>\n\n"
                        f"✅ اشتراک فعال شد\n"
                        f"📅 مدت: ۶ ماه\n\n"
                        f"🎁 کد معرف:\n<code>{referral_code}</code>",
                        parse_mode="HTML",
                        reply_markup=main_menu_keyboard()
                    )
            
            await callback.message.edit_caption(
                caption=callback.message.caption + "\n\n✅ <b>تایید شد</b>",
                parse_mode="HTML"
            )
            await callback.answer("✅ تایید شد")
        
        else:  # reject
            # Update sheet
            header = rows[0]
            try:
                status_idx = header.index("status")
                approved_at_idx = header.index("approved_at")
                approved_by_idx = header.index("approved_by")
                
                row[status_idx] = "rejected"
                row[approved_at_idx] = now_iso()
                row[approved_by_idx] = str(callback.from_user.id)
                await update_row("Purchases", purchase_idx, row)
            except ValueError as e:
                logger.error(f"Column not found: {e}")
                await callback.answer("❌ خطای ساختار شیت!", show_alert=True)
                return

                
                await bot.send_message(
                    user_id,
                    "❌ <b>سفارش رد شد</b>\n\n"
                    "با پشتیبانی تماس بگیرید.",
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard()
                )
            
            await callback.message.edit_caption(
                caption=callback.message.caption + "\n\n❌ <b>رد شد</b>",
                parse_mode="HTML"
            )
            await callback.answer("❌ رد شد")
    
    except Exception as e:
        logger.exception(f"Error in card approval: {e}")
        await callback.answer(f"❌ خطا: {e}", show_alert=True)


# ============================================
# ADMIN APPROVAL
# ============================================
@dp.callback_query_handler(lambda c: (c.data.startswith("approve_") or c.data.startswith("reject_")) and not c.data.startswith("approve_card_") and not c.data.startswith("reject_card_") and not c.data.startswith("approve_wd_") and not c.data.startswith("reject_wd_"))
async def callback_admin_purchase(callback: types.CallbackQuery):
    """Admin purchase approval"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ شما ادمین نیستید!", show_alert=True)
        return
    
    parts = callback.data.split("_")
    action = parts[0]
    purchase_id = parts[1]
    user_id = int(parts[2])
    
    rows = await get_all_rows("Purchases")
    purchase_row = None
    purchase_idx = None
    
    for idx, row in enumerate(rows[1:], start=2):
        if row and row[0] == purchase_id:
            purchase_row = row
            purchase_idx = idx
            break
    
    if not purchase_row:
        await callback.answer("❌ سفارش یافت نشد!", show_alert=True)
        return
    
    product = purchase_row[3]
    amount_usd = float(purchase_row[4])
    payment_method = purchase_row[6]
    
    if action == "approve":
        purchase_row[9] = "approved"
        purchase_row[11] = now_iso()
        purchase_row[12] = str(callback.from_user.id)
        await update_row("Purchases", purchase_idx, purchase_row)
        
        user_result = await find_user(user_id)
        username = user_result[1][1] if user_result else ""
        
        # ✅ چک نوع خرید
        is_reserve = product.startswith("reserve_")
        is_complete = product.startswith("complete_")
        is_gift = product.startswith("gift_")
        
        # ─────────────────────────────────────────────────────────
        # حالت ۱: پیش‌پرداخت (رزرو)
        # ─────────────────────────────────────────────────────────
        if is_reserve:
            actual_product = product.replace("reserve_", "")
            
            # ثبت رزرو
            await set_user_reserve(user_id, actual_product, 2.0)
            
            # پیام به کاربر
            product_name = "ویژه" if actual_product == "premium" else "معمولی"
            total = PREMIUM_PRICE if actual_product == "premium" else NORMAL_PRICE
            remaining = total - 2.0
            
            try:
                await bot.send_message(
                    user_id,
                    f"✅ <b>پیش‌پرداخت تایید شد!</b>\n\n"
                    f"🎉 جایگاه شما رزرو شد!\n\n"
                    f"📦 محصول: اشتراک {product_name}\n"
                    f"💵 پرداخت شده: <b>$2.00</b>\n"
                    f"💰 باقیمانده: <b>${remaining:.2f}</b>\n\n"
                    f"⚠️ برای فعال‌سازی کامل، باید مبلغ باقیمانده را پرداخت کنید.\n\n"
                    f"💡 از منوی 💰 کیف پول → 💵 تکمیل پیش‌پرداخت استفاده کنید.",
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard()
                )
            except Exception as e:
                logger.exception(f"Failed to send reserve confirmation: {e}")
            
            # پیام ادمین
            try:
                await callback.message.edit_caption(
                    caption=callback.message.caption + "\n\n✅ <b>رزرو ثبت شد</b>",
                    parse_mode="HTML"
                )
            except:
                try:
                    await callback.message.edit_text(
                        callback.message.text + "\n\n✅ <b>رزرو ثبت شد</b>",
                        parse_mode="HTML"
                    )
                except:
                    pass
            
            await callback.answer("✅ رزرو ثبت شد")
        
        # ─────────────────────────────────────────────────────────
        # حالت ۲: تکمیل پیش‌پرداخت
        # ─────────────────────────────────────────────────────────
        elif is_complete:
            actual_product = product.replace("complete_", "")
            
            # دریافت اطلاعات رزرو
            reserve = await get_user_reserve_status(user_id)
            
            if not reserve["has_reserve"]:
                logger.error(f"Complete payment but no reserve for {user_id}")
                await callback.answer("❌ رزرو یافت نشد!", show_alert=True)
                return
            
            # ✅ فعال‌سازی اشتراک
            await activate_subscription(user_id, username, actual_product, payment_method)
            
            # ✅ محاسبه پورسانت با کل مبلغ (رزرو + تکمیل)
            total_paid = reserve["amount_paid"] + amount_usd
            await process_referral_commission(purchase_id, user_id, total_paid)
            
            # ✅ پاک کردن رزرو
            await clear_user_reserve(user_id)
            
            # ✅ ارسال لینک معرف و پیام تبریک
            try:
                result = await find_user(user_id)
                if result:
                    _, user_row = result
                    referral_code = user_row[4] if len(user_row) > 4 else ""
                    
                    kb_share = social_share_keyboard("ویژه" if actual_product == "premium" else "معمولی")
                    
                    await bot.send_message(
                        user_id,
                        f"🎉 <b>اشتراک فعال شد!</b>\n\n"
                        f"✅ پرداخت تکمیل شد\n"
                        f"📅 مدت: ۶ ماه\n\n"
                        f"🎁 کد معرف شما:\n<code>{referral_code}</code>\n\n"
                        f"💡 با دعوت دوستان پورسانت کسب کنید!\n\n"
                        f"📢 این خبر خوب را به اشتراک بگذارید:",
                        parse_mode="HTML",
                        reply_markup=kb_share
                    )
                    logger.info(f"✅ Completed pre-payment for {user_id}")
            except Exception as e:
                logger.exception(f"Failed to send completion message: {e}")
            
            # پیام ادمین
            try:
                await callback.message.edit_caption(
                    caption=callback.message.caption + "\n\n✅ <b>تکمیل شد و فعال شد</b>",
                    parse_mode="HTML"
                )
            except:
                try:
                    await callback.message.edit_text(
                        callback.message.text + "\n\n✅ <b>تکمیل شد و فعال شد</b>",
                        parse_mode="HTML"
                    )
                except:
                    pass
            
            await callback.answer("✅ تکمیل و فعال شد")
        
        # ─────────────────────────────────────────────────────────
        # حالت ۳: هدیه
        # ─────────────────────────────────────────────────────────
        elif is_gift:
            actual_product = product.replace("gift_", "")
            
            # دریافت پیام هدیه
            gift_message = ""
            if user_id in user_states:
                gift_message = user_states[user_id].get("gift_message", "")
            
            # ساخت گیفت کارت
            gift_code = await create_gift_card(actual_product, user_id, username, gift_message)
            
            if gift_code:
                bot_username = (await bot.get_me()).username
                gift_link = f"https://t.me/{bot_username}?start=gift_{gift_code}"
                
                try:
                    await bot.send_message(
                        user_id,
                        f"🎁 <b>هدیه شما آماده شد!</b>\n\n"
                        f"🔗 <b>لینک هدیه:</b>\n<code>{gift_link}</code>\n\n"
                        f"💡 این لینک را برای دوست خود ارسال کنید.\n"
                        f"او با کلیک روی لینک، اشتراک فعال می‌شود!",
                        parse_mode="HTML",
                        reply_markup=main_menu_keyboard()
                    )
                    logger.info(f"✅ Gift card sent to {user_id}")
                except Exception as e:
                    logger.exception(f"Failed to send gift: {e}")
            
            # حذف state
            user_states.pop(user_id, None)
            
            # پیام ادمین
            try:
                await callback.message.edit_caption(
                    caption=callback.message.caption + "\n\n✅ <b>هدیه ساخته شد</b>",
                    parse_mode="HTML"
                )
            except:
                try:
                    await callback.message.edit_text(
                        callback.message.text + "\n\n✅ <b>هدیه ساخته شد</b>",
                        parse_mode="HTML"
                    )
                except:
                    pass
            
            await callback.answer("✅ هدیه ساخته شد")
        
        # ─────────────────────────────────────────────────────────
        # حالت ۴: خرید عادی
        # ─────────────────────────────────────────────────────────
        else:
            try:
                await activate_subscription(user_id, username, product, payment_method)
                await process_referral_commission(purchase_id, user_id, amount_usd)
            except Exception as e:
                logger.exception(f"Failed to activate: {e}")
            
            try:
                result = await find_user(user_id)
                if result:
                    _, user_row = result
                    referral_code = user_row[4] if len(user_row) > 4 else ""
                    
                    kb_share = social_share_keyboard("ویژه" if product == "premium" else "معمولی")
                    
                    await bot.send_message(
                        user_id,
                        f"🎉 <b>پرداخت تایید شد!</b>\n\n"
                        f"✅ اشتراک فعال شد\n"
                        f"📅 مدت: ۶ ماه\n\n"
                        f"🎁 کد معرف:\n<code>{referral_code}</code>\n\n"
                        f"💡 با دعوت دوستان پورسانت کسب کنید!\n\n"
                        f"📢 این خبر را به اشتراک بگذارید:",
                        parse_mode="HTML",
                        reply_markup=kb_share
                    )
                    logger.info(f"✅ Approval sent to {user_id}")
            except Exception as e:
                logger.exception(f"Failed to send approval: {e}")
            
            try:
                await callback.message.edit_caption(
                    caption=callback.message.caption + "\n\n✅ <b>تایید شد</b>",
                    parse_mode="HTML"
                )
            except:
                try:
                    await callback.message.edit_text(
                        callback.message.text + "\n\n✅ <b>تایید شد</b>",
                        parse_mode="HTML"
                    )
                except:
                    pass
            
            await callback.answer("✅ تایید شد")
    
    else:
        purchase_row[9] = "rejected"
        purchase_row[11] = now_iso()
        purchase_row[12] = str(callback.from_user.id)
        await update_row("Purchases", purchase_idx, purchase_row)
        
        try:
            await bot.send_message(
                user_id,
                "❌ <b>سفارش رد شد</b>\n\n"
                "با پشتیبانی تماس بگیرید.",
                parse_mode="HTML"
            )
        except:
            pass
        
        try:
            await callback.message.edit_caption(
                caption=callback.message.caption + "\n\n❌ <b>رد شد</b>",
                parse_mode="HTML"
            )
        except:
            try:
                await callback.message.edit_text(
                    callback.message.text + "\n\n❌ <b>رد شد</b>",
                    parse_mode="HTML"
                )
            except:
                pass
        
        await callback.answer("❌ رد شد")

# ============================================
# WALLET SYSTEM
# ============================================
@dp.message_handler(lambda msg: msg.text == "💰 کیف پول")
async def handle_wallet(message: types.Message):
    """Wallet handler"""
    user = message.from_user
    
    if not await check_membership_for_all_messages(message):
        return
    
    balance = await get_user_balance(user.id)
    reserve = await get_user_reserve_status(user.id)
    
    rows = await get_all_rows("Referrals")
    total_referrals = sum(1 for row in rows[1:] if row and str(row[0]) == str(user.id))
    
    kb = wallet_keyboard(balance, reserve["has_reserve"])
    
    reserve_note = ""
    if reserve["has_reserve"]:
        product_name = "ویژه" if reserve["product"] == "premium" else "معمولی"
        total = PREMIUM_PRICE if reserve["product"] == "premium" else NORMAL_PRICE
        remaining = total - reserve["amount_paid"]
        
        reserve_note = (
            f"\n\n⏳ <b>پیش‌پرداخت فعال:</b>\n"
            f"📦 {product_name}\n"
            f"💵 پرداخت: ${reserve['amount_paid']:.2f}\n"
            f"💰 باقیمانده: ${remaining:.2f}"
        )
    
    await send_and_record(
        user.id,
        f"💰 <b>کیف پول</b>\n\n"
        f"💵 موجودی: <b>${balance:.2f}</b>\n"
        f"👥 معرفی: <b>{total_referrals}</b>{reserve_note}\n\n"
        f"{'💡 حداقل برداشت: $10' if balance < 10 else '✅ می‌توانید برداشت کنید'}",
        parse_mode="HTML",
        reply_markup=kb
    )


@dp.callback_query_handler(lambda c: c.data == "complete_reserve")
async def callback_complete_reserve(callback: types.CallbackQuery):
    """تکمیل پیش‌پرداخت"""
    user = callback.from_user
    
    reserve = await get_user_reserve_status(user.id)
    
    if not reserve["has_reserve"]:
        await callback.answer("شما رزروی ندارید!", show_alert=True)
        return
    
    product = reserve["product"]
    paid = reserve["amount_paid"]
    total = PREMIUM_PRICE if product == "premium" else NORMAL_PRICE
    remaining = total - paid
    
    # روش پرداخت
    kb = payment_method_keyboard(f"complete_{product}")
    
    await callback.message.edit_text(
        f"💳 <b>تکمیل پیش‌پرداخت</b>\n\n"
        f"📦 محصول: {'ویژه' if product == 'premium' else 'معمولی'}\n"
        f"💵 پرداخت شده: <b>${paid:.2f}</b>\n"
        f"💰 مبلغ نهایی: <b>${remaining:.2f}</b>\n\n"
        f"روش پرداخت را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()


# 

@dp.callback_query_handler(lambda c: c.data == "wallet")
async def callback_wallet(callback: types.CallbackQuery):
    """Wallet callback"""
    user = callback.from_user
    balance = await get_user_balance(user.id)
    rows = await get_all_rows("Referrals")
    total_referrals = sum(1 for row in rows[1:] if row and str(row[0]) == str(user.id))
    kb = wallet_keyboard(balance)
    
    await callback.message.edit_text(
        f"💰 <b>کیف پول</b>\n\n"
        f"💵 موجودی: <b>${balance:.2f}</b>\n"
        f"👥 معرفی: <b>{total_referrals}</b>\n\n"
        f"{'💡 حداقل: $10' if balance < 10 else '✅ برداشت کنید'}",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "withdraw")
async def callback_withdraw(callback: types.CallbackQuery):
    """Withdraw"""
    user = callback.from_user
    balance = await get_user_balance(user.id)
    
    if balance < 10:
        await callback.answer("❌ حداقل $10!", show_alert=True)
        return
    
    kb = withdrawal_method_keyboard()
    await callback.message.edit_text(
        f"💸 <b>برداشت</b>\n\n"
        f"💵 موجودی: <b>${balance:.2f}</b>\n"
        f"💡 حداقل: <b>$10</b>\n\n"
        f"روش را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "wallet_history")
async def callback_wallet_history(callback: types.CallbackQuery):
    """History"""
    user = callback.from_user
    rows = await get_all_rows("Referrals")
    user_referrals = [row for row in rows[1:] if row and str(row[0]) == str(user.id)]
    
    if not user_referrals:
        await callback.answer("هنوز پورسانتی ندارید.", show_alert=True)
        return
    
    history_text = "📊 <b>تاریخچه</b>\n\n"
    for row in user_referrals[-10:]:
        level = row[2] if len(row) > 2 else ""
        amount = row[3] if len(row) > 3 else "0"
        date = row[6] if len(row) > 6 else ""
        try:
            date_obj = parse_iso(date)
            date_str = date_obj.strftime("%Y/%m/%d") if date_obj else date
        except:
            date_str = date
        history_text += f"• ${amount} (سطح {level}) - {date_str}\n"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 بازگشت", callback_data="wallet"))
    
    await callback.message.edit_text(history_text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("withdraw_"))
async def callback_withdraw_method(callback: types.CallbackQuery):
    """Withdraw method"""
    user = callback.from_user
    method = callback.data.split("_")[1]
    balance = await get_user_balance(user.id)
    
    if balance < 10:
        await callback.answer("❌ موجودی کم!", show_alert=True)
        return
    
    user_states[user.id] = {
        "state": f"awaiting_withdraw_{method}_info",
        "method": method,
        "balance": balance
    }
    
    if method == "card":
        await callback.message.edit_text(
            f"💳 <b>برداشت به کارت</b>\n\n"
            f"💵 موجودی: <b>${balance:.2f}</b>\n\n"
            f"فرمت:\n<code>مبلغ شماره_کارت</code>\n\n"
            f"مثال:\n<code>15 6037991234567890</code>",
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            f"🪙 <b>برداشت به تتر</b>\n\n"
            f"💵 موجودی: <b>${balance:.2f}</b>\n\n"
            f"فرمت:\n<code>مبلغ آدرس_کیف_پول</code>\n\n"
            f"مثال:\n<code>20 0x1234...5678</code>",
            parse_mode="HTML"
        )
    
    await callback.answer()

@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state", "").startswith("awaiting_withdraw_"))
async def handle_withdrawal_request(message: types.Message):
    """Handle withdrawal request"""
    user = message.from_user
    state = user_states.get(user.id, {})
    method = state.get("method")
    balance = state.get("balance", 0)
    
    parts = message.text.strip().split(maxsplit=1)
    
    if len(parts) < 2:
        await message.reply(
            "❌ فرمت نادرست!\n\n"
            "مثال صحیح:\n"
            "<code>15 6037991234567890</code> (برای کارت)\n"
            "<code>20 0x1234...5678</code> (برای تتر)",
            parse_mode="HTML"
        )
        return
    
    try:
        amount = float(parts[0])
    except:
        await message.reply("❌ مبلغ نامعتبر!")
        return
    
    if amount < 10:
        await message.reply("❌ حداقل برداشت $10 است!")
        return
    
    if amount > balance:
        await message.reply(f"❌ موجودی کافی نیست! موجودی شما: ${balance:.2f}")
        return
    
    destination = parts[1]
    
    # Validate destination format
    if method == "usdt":
        if not destination.startswith("0x") or len(destination) < 20:
            await message.reply(
                "❌ آدرس ولت نامعتبر!\n\n"
                "آدرس BEP20 باید با 0x شروع شود.\n"
                "مثال: <code>0x1234567890abcdef1234567890abcdef12345678</code>",
                parse_mode="HTML"
            )
            return
    
    withdrawal_id = generate_withdrawal_id()
    
    if method == "card":
        await append_row("Withdrawals", [
            withdrawal_id,
            str(user.id),
            str(amount),
            "card",
            "",
            destination,
            "pending",
            now_iso(),
            "",
            "",
            ""
        ])
    else:
        await append_row("Withdrawals", [
            withdrawal_id,
            str(user.id),
            str(amount),
            "usdt",
            destination,
            "",
            "pending",
            now_iso(),
            "",
            "",
            ""
        ])
    
    user_states.pop(user.id, None)
    
    await message.reply(
        f"✅ <b>درخواست برداشت ثبت شد!</b>\n\n"
        f"🔢 شناسه: <code>{withdrawal_id}</code>\n"
        f"💰 مبلغ: <b>${amount}</b>\n"
        f"🔄 روش: {'کارت بانکی' if method == 'card' else 'تتر BEP20'}\n\n"
        f"⏳ پس از بررسی، مبلغ واریز می‌شود.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )
    
    # Send to admin with inline buttons
    if ADMIN_TELEGRAM_ID:
        try:
            # Get row index for callback
            rows = await get_all_rows("Withdrawals")
            withdrawal_idx = len(rows)  # Last row
            
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton(
                    "✅ پرداخت شد", 
                    callback_data=f"approve_wd_{withdrawal_id}_{user.id}_{withdrawal_idx}"
                ),
                InlineKeyboardButton(
                    "❌ رد", 
                    callback_data=f"reject_wd_{withdrawal_id}_{user.id}_{withdrawal_idx}"
                )
            )
            
            await bot.send_message(
                int(ADMIN_TELEGRAM_ID),
                f"💸 <b>درخواست برداشت جدید</b>\n\n"
                f"👤 <b>کاربر:</b> {user.full_name}\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"💰 <b>مبلغ:</b> ${amount}\n"
                f"🔄 <b>روش:</b> {'کارت بانکی' if method == 'card' else 'تتر BEP20'}\n"
                f"📋 <b>مقصد:</b>\n<code>{destination}</code>\n\n"
                f"🔢 <b>شناسه:</b> <code>{withdrawal_id}</code>",
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            logger.exception(f"Failed to notify admin: {e}")

"""
Telegram Subscription Bot - Part 3B (FINAL)
Admin Commands, Support, Referral & Startup
"""

async def process_withdrawal_approval(withdrawal_id: str, withdrawal_idx: int, 
                                      user_id: int, amount: float, 
                                      method: str, destination: str, txid: str):
    """Process withdrawal approval"""
    try:
        # Update sheet
        rows = await get_all_rows("Withdrawals")
        if withdrawal_idx >= len(rows):
            return
        
        row = rows[withdrawal_idx - 1]
        header = rows[0]
        
        status_idx = header.index("status")
        processed_at_idx = header.index("processed_at")
        processed_by_idx = header.index("processed_by")
        notes_idx = header.index("notes")
        
        row[status_idx] = "completed"
        row[processed_at_idx] = now_iso()
        row[processed_by_idx] = "admin"
        row[notes_idx] = f"TXID: {txid}"
        
        await update_row("Withdrawals", withdrawal_idx, row)
        
        # Deduct from balance
        await update_user_balance(user_id, amount, add=False)
        
        # Send to user
        txid_display = f"\n🔗 <b>TXID:</b> <code>{txid}</code>" if method == "usdt" else ""
        
        await bot.send_message(
            user_id,
            f"✅ <b>برداشت انجام شد!</b>\n\n"
            f"💰 مبلغ: <b>${amount}</b>\n"
            f"🔢 شناسه: <code>{withdrawal_id}</code>{txid_display}\n\n"
            f"مبلغ به {'کارت' if method == 'card' else 'کیف پول'} شما واریز شد.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )
        
        logger.info(f"✅ Withdrawal {withdrawal_id} approved for user {user_id}")
    
    except Exception as e:
        logger.exception(f"Failed to process withdrawal approval: {e}")



# ============================================
# ADMIN WITHDRAWAL APPROVAL
# ============================================
@dp.callback_query_handler(lambda c: c.data.startswith("approve_wd_") or c.data.startswith("reject_wd_"))
async def callback_admin_withdrawal(callback: types.CallbackQuery):
 
    """Admin withdrawal approval from Telegram"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ شما ادمین نیستید!", show_alert=True)
        return
    
    parts = callback.data.split("_")
    action = parts[0]
    withdrawal_id = parts[2]
    user_id = int(parts[3])
    withdrawal_idx = int(parts[4])
    
    try:
        rows = await get_all_rows("Withdrawals")
        
        if withdrawal_idx < 2 or withdrawal_idx > len(rows):
            await callback.answer("❌ درخواست یافت نشد!", show_alert=True)
            return
        
        row = rows[withdrawal_idx - 1]
        amount = float(row[2]) if len(row) > 2 else 0
        method = row[3] if len(row) > 3 else ""
        destination = row[4] if len(row) > 4 and method == "usdt" else (row[5] if len(row) > 5 else "")
        
        if action == "approve":
            # Ask for TXID if USDT
            if method == "usdt":
                # Store pending approval in user_states
                user_states[callback.from_user.id] = {
                    "state": "awaiting_txid_for_withdrawal",
                    "withdrawal_id": withdrawal_id,
                    "withdrawal_idx": withdrawal_idx,
                    "user_id": user_id,
                    "amount": amount,
                    "destination": destination
                }
                
                await callback.message.edit_text(
                    callback.message.text + "\n\n⏳ <b>در حال پردازش...</b>\n\n"
                    "لطفاً <b>Transaction ID (TXID)</b> واریز را ارسال کنید:",
                    parse_mode="HTML"
                )
                await callback.answer("لطفاً TXID را ارسال کنید")
            else:
                # Card payment - process immediately
                await process_withdrawal_approval(
                    withdrawal_id, withdrawal_idx, user_id, amount, 
                    method, destination, "manual_card_payment"
                )
                
                await callback.message.edit_text(
                    callback.message.text + "\n\n✅ <b>تایید شد و پردازش شد</b>",
                    parse_mode="HTML"
                )
                await callback.answer("✅ تایید شد")
        
        else:  # reject
            # Update sheet
            header = rows[0]
            status_idx = header.index("status")
            processed_at_idx = header.index("processed_at")
            processed_by_idx = header.index("processed_by")
            
            row[status_idx] = "rejected"
            row[processed_at_idx] = now_iso()
            row[processed_by_idx] = str(callback.from_user.id)
            await update_row("Withdrawals", withdrawal_idx, row)
            
            try:
                await bot.send_message(
                    user_id,
                    f"❌ <b>درخواست برداشت رد شد</b>\n\n"
                    f"🔢 شناسه: <code>{withdrawal_id}</code>\n\n"
                    f"لطفاً با پشتیبانی تماس بگیرید.",
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard()
                )
            except:
                pass
            
            await callback.message.edit_text(
                callback.message.text + "\n\n❌ <b>رد شد</b>",
                parse_mode="HTML"
            )
            await callback.answer("❌ رد شد")
    
    except Exception as e:
        logger.exception(f"Error in withdrawal approval: {e}")
        await callback.answer(f"❌ خطا: {e}", show_alert=True)


# ============================================
# REFERRAL SYSTEM
# ============================================
@dp.message_handler(lambda msg: msg.text == "🎁 دعوت دوستان")
async def handle_referral(message: types.Message):
    """Referral handler"""
    user = message.from_user
    
    # چک عضویت
    if not await check_membership_for_all_messages(message):
        return
        
    # ✅ چک رزرو
    if not await check_reserve_block(message):
        return
    
    # ✅ چک خرید تایید شده
    purchases_rows = await get_all_rows("Purchases")
    has_purchase = False
    
    for row in purchases_rows[1:]:
        if not row or len(row) < 10:
            continue
        if str(row[1]) == str(user.id) and row[9] == "approved":
            has_purchase = True
            break
    
    if not has_purchase:
        await message.reply(
            "⚠️ <b>برای استفاده از سیستم معرفی، ابتدا باید اشتراک خریداری کنید.</b>\n\n"
            "پس از خرید و تایید، کد معرف فعال می‌شود.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )
        return
    
    result = await find_user(user.id)
    
    if not result:
        await message.reply("❌ خطا در بارگذاری اطلاعات.", reply_markup=main_menu_keyboard())
        return
    
    _, row = result
    referral_code = row[4] if len(row) > 4 else ""
    
    rows = await get_all_rows("Referrals")
    level1_count = sum(1 for r in rows[1:] if r and str(r[0]) == str(user.id) and r[2] == "1")
    level2_count = sum(1 for r in rows[1:] if r and str(r[0]) == str(user.id) and r[2] == "2")
    
    total_earned = 0
    for r in rows[1:]:
        if r and str(r[0]) == str(user.id) and r[4] == "paid":
            try:
                total_earned += float(r[3])
            except:
                pass
    
    bot_username = (await bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"

    # ✅ نرخ پورسانت دینامیک - اگه بوست داشته باشه از اون نرخ نشون بده
    user_boost = await get_user_boost(user.id)
    l1_rate = user_boost["level1"] if user_boost else 8
    l2_rate = user_boost["level2"] if user_boost else 12
    boost_badge = "🌟 " if user_boost else ""
    
    # ✅ آپدیت #19: اضافه دکمه اشتراک‌گذاری لینک معرف
    import urllib.parse
    share_text = f"🎁 از این لینک عضو شو و من هم پورسانت میگیرم!"
    encoded_text = urllib.parse.quote(share_text)
    encoded_link = urllib.parse.quote(referral_link)
    
    kb_share = InlineKeyboardMarkup(row_width=2)
    kb_share.add(
        InlineKeyboardButton(
            "📱 اشتراک در تلگرام",
            url=f"https://t.me/share/url?url={encoded_link}&text={encoded_text}"
        ),
        InlineKeyboardButton(
            "💬 اشتراک در واتساپ",
            url=f"https://wa.me/?text={encoded_text}%20{encoded_link}"
        )
    )
    kb_share.add(
        InlineKeyboardButton(
            "🐦 اشتراک در توییتر",
            url=f"https://twitter.com/intent/tweet?text={encoded_text}&url={encoded_link}"
        )
    )
    
    await message.reply(
        f"🎁 <b>دعوت دوستان</b>\n\n"
        f"🔗 <b>لینک:</b>\n<code>{referral_link}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>آمار:</b>\n"
        f"👥 سطح 1: {level1_count} نفر ({boost_badge}{l1_rate}%)\n"
        f"👥 سطح 2: {level2_count} نفر ({boost_badge}{l2_rate}%)\n"
        f"💰 کل درآمد: <b>${total_earned:.2f}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>کسب درآمد:</b>\n"
        f"• از لینک بالا دعوت کنید\n"
        f"• هر خرید = پورسانت\n"
        f"• سطح 1: {l1_rate}%\n"
        f"• سطح 2: {l2_rate}%\n\n"
        f"📢 لینک خود را به اشتراک بگذارید:",
        parse_mode="HTML",
        reply_markup=kb_share
    )


# ============================================
# SUPPORT SYSTEM
# ============================================
@dp.message_handler(lambda msg: msg.text == "💬 پشتیبانی")
async def handle_support(message: types.Message):
    """Support handler"""
    
    # ✅ چک عضویت
    if not await check_membership_for_all_messages(message):
        return
    
    # ✅ چک رزرو
    if not await check_reserve_block(message):
        return
    
    user_states[message.from_user.id] = {"state": "awaiting_support_message"}
    
    await message.reply(
        "💬 <b>پشتیبانی</b>\n\n"
        "پیام خود را ارسال کنید.\n"
        "به زودی پاسخ داده می‌شود.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )


@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_support_message")
async def handle_support_message(message: types.Message):
    """Handle support message"""
    user = message.from_user
    ticket_id = generate_ticket_id()
    
    await append_row("Tickets", [
        ticket_id, str(user.id), user.username or "",
        "پشتیبانی", message.text, "open",
        now_iso(), "", ""
    ])
    
    user_states.pop(user.id, None)
    
    await message.reply(
        f"✅ <b>تیکت ثبت شد!</b>\n\n"
        f"🔢 <code>{ticket_id}</code>\n\n"
        f"⏳ به زودی پاسخ می‌دهیم.",
        parse_mode="HTML"
    )
    
    if ADMIN_TELEGRAM_ID:
        try:
            await bot.send_message(
                int(ADMIN_TELEGRAM_ID),
                f"🎫 <b>تیکت جدید</b>\n\n"
                f"👤 {user.full_name} (@{user.username or 'ندارد'})\n"
                f"🆔 <code>{user.id}</code>\n"
                f"🔢 <code>{ticket_id}</code>\n\n"
                f"📝 {message.text}\n\n"
                f"پاسخ:\n<code>/reply {ticket_id} متن_پاسخ</code>",
                parse_mode="HTML"
            )
        except:
            pass

@dp.message_handler(lambda msg: msg.text == "📚 راهنما")
async def handle_help(message: types.Message):
    """Help handler"""
    
    # ✅ چک عضویت
    if not await check_membership_for_all_messages(message):
        return
  
    # ✅ چک رزرو
    if not await check_reserve_block(message):
        return
    
    await message.reply(
        "📚 <b>راهنما</b>\n\n"
        "🆓 <b>تست کانال:</b>\n"
        "• ۵ دقیقه رایگان\n"
        "• فقط یکبار\n\n"
        "💎 <b>خرید:</b>\n"
        "• معمولی: $5 (۶ ماه)\n"
        "• ویژه: $20 (۶ ماه)\n\n"
        "💰 <b>کیف پول:</b>\n"
        "• موجودی و برداشت\n"
        "• حداقل: $10\n\n"
        "🎁 <b>دعوت:</b>\n"
        "• سطح 1: 8% (تا ۱۰ معرفی)\n"
        "• سطح 2: 12%\n\n"
        "✨ <b>پاداش ۱۰ معرفی:</b>\n"
        "• با رسیدن به ۱۰ معرفی مستقیم\n"
        "• سطح 1: 10% (بجای ۸%)\n"
        "• سطح 2: 15% (بجای ۱۲%)\n"
        "• خودکار فعال می‌شود!\n\n"
        "💬 <b>پشتیبانی:</b>\n"
        "• ثبت تیکت\n"
        "• پاسخ سریع\n\n"
        "📊 <b>گزارش ماهانه:</b>\n"
        "• /report - مشاهده گزارش فعالیت\n"
        "• ارسال خودکار اول هر ماه",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )


@dp.message_handler(commands=["report"])
async def cmd_report(message: types.Message):
    """Show monthly report"""
    user = message.from_user
    
    # چک عضویت
    if not await check_membership_for_all_messages(message):
        return

    # ✅ چک رزرو
    if not await check_reserve_block(message):
        return
    
    report = await generate_monthly_report(user.id)
    
    if report:
        await message.reply(report, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else:
        await message.reply(
            "❌ خطا در ساخت گزارش.\n"
            "لطفاً بعداً تلاش کنید.",
            reply_markup=main_menu_keyboard()
        )

@dp.message_handler(commands=["redeem"])
async def cmd_redeem_secret(message: types.Message):
    """Secret command: redeem boost code - نه توی راهنما، نه توی منو"""
    user = message.from_user
    args = message.get_args()
    
    if not args:
        # اگه بدون آرگیمنت بزنه، هیچ پاسخی نده تا مخفی بمونه
        return
    
    code = args.strip().upper()
    
    result = await validate_and_apply_boost(code, user.id)
    
    if result is None:
        # کد نامعتبر - هیچ پاسخی نده تا مخفی بمونه
        return
    
    if result.get("error") == "already_boosted":
        await message.reply(
            "✅ <b>شما قبلاً یک آفر ویژه فعال دارید!</b>",
            parse_mode="HTML"
        )
        return
    
    # موفق شد
    await message.reply(
        f"🌟 <b>آفر ویژه فعال شد!</b>\n\n"
        f"💎 سطح 1: <b>{result['level1_percent']}%</b>\n"
        f"💎 سطح 2: <b>{result['level2_percent']}%</b>\n\n"
        f"🎯 از این لحظه پورسانت شما با نرخ جدید محاسبه میشه!",
        parse_mode="HTML"
    )
    
    # نوتیفیکیشن به ادمین
    if ADMIN_TELEGRAM_ID:
        try:
            await bot.send_message(
                int(ADMIN_TELEGRAM_ID),
                f"🔔 <b>بوست فعال شد</b>\n\n"
                f"👤 کاربر: {user.full_name} (@{user.username or 'ندارد'})\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"🎟 کد: <code>{result['code']}</code>\n"
                f"📊 سطح 1: {result['level1_percent']}% | سطح 2: {result['level2_percent']}%",
                parse_mode="HTML"
            )
        except:
            pass


@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_txid_for_withdrawal")
async def handle_txid_for_withdrawal(message: types.Message):
    """Handle TXID from admin for withdrawal approval"""
    if not is_admin(message.from_user.id):
        return
    
    state = user_states.get(message.from_user.id, {})
    withdrawal_id = state.get("withdrawal_id")
    withdrawal_idx = state.get("withdrawal_idx")
    user_id = state.get("user_id")
    amount = state.get("amount")
    destination = state.get("destination")
    
    txid = message.text.strip()
    
    if len(txid) < 20:
        await message.reply("❌ TXID نامعتبر است. لطفاً TXID صحیح را ارسال کنید.")
        return
    
    # Process approval
    await process_withdrawal_approval(
        withdrawal_id, withdrawal_idx, user_id, 
        amount, "usdt", destination, txid
    )
    
    user_states.pop(message.from_user.id, None)
    
    await message.reply(
        f"✅ <b>برداشت تایید و پردازش شد</b>\n\n"
        f"💰 مبلغ: ${amount}\n"
        f"🔗 TXID: <code>{txid}</code>\n\n"
        f"کاربر مطلع شد.",
        parse_mode="HTML"
    )


@dp.message_handler(lambda msg: msg.text == "🔙 منوی عادی")
async def handle_back_to_user_menu(message: types.Message):
    """برگشت از منوی ادمین به منوی کاربر عادی"""
    if not is_admin(message.from_user.id):
        return
    
    await message.reply(
        "🔄 بازگشت به منوی کاربر",
        reply_markup=main_menu_keyboard()
    )


@dp.message_handler(lambda msg: msg.text == "📊 آمار سیستم")
async def handle_admin_stats_menu(message: types.Message):
    """نمایش آمار سیستم"""
    if not is_admin(message.from_user.id):
        return
    
    # استفاده از دستور /dashboard موجود
    await cmd_admin_dashboard(message)


@dp.message_handler(lambda msg: msg.text == "📢 ارسال پیام")
async def handle_admin_message_menu(message: types.Message):
    """منوی ارسال پیام"""
    if not is_admin(message.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📤 پیام به همه", callback_data="admin_msg_all"),
        InlineKeyboardButton("📋 پیام به گروه", callback_data="admin_msg_group"),
        InlineKeyboardButton("👤 پیام به فرد خاص", callback_data="admin_msg_single"),
    )
    
    await message.reply(
        "📢 <b>ارسال پیام</b>\n\n"
        "نوع ارسال را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )


@dp.callback_query_handler(lambda c: c.data == "admin_msg_all")
async def callback_admin_msg_all(callback: types.CallbackQuery):
    """راهنمای broadcast"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📤 <b>پیام به همه کاربران</b>\n\n"
        "از دستور زیر استفاده کنید:\n\n"
        "<code>/broadcast پیام شما</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "admin_msg_group")
async def callback_admin_msg_group(callback: types.CallbackQuery):
    """راهنمای msklist"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    # استفاده مستقیم از منوی msklist
    await callback.message.edit_text(
        "📋 <b>پیام به گروه</b>\n\n"
        "از دستور زیر استفاده کنید:\n\n"
        "<code>/msklist</code>\n\n"
        "یا منوی زیر را انتخاب کنید:",
        parse_mode="HTML"
    )
    
    # فراخوانی مستقیم منوی msklist
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("✅ فعال", callback_data="msklist_active"),
        InlineKeyboardButton("⏰ منقضی", callback_data="msklist_expired"),
        InlineKeyboardButton("🎁 معرف کرده", callback_data="msklist_referrers"),
        InlineKeyboardButton("🎟 هدیه خریده", callback_data="msklist_gift_buyers"),
        InlineKeyboardButton("🌟 بوست فعال", callback_data="msklist_boosted"),
        InlineKeyboardButton("📝 لیست دستی", callback_data="msklist_manual"),
    )
    
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "admin_msg_single")
async def callback_admin_msg_single(callback: types.CallbackQuery):
    """راهنمای msg"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    await callback.message.edit_text(
        "👤 <b>پیام به فرد خاص</b>\n\n"
        "از دستور زیر استفاده کنید:\n\n"
        "<code>/msg USER_ID پیام شما</code>\n\n"
        "مثال:\n"
        "<code>/msg 123456789 سلام</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message_handler(lambda msg: msg.text == "💳 تایید خریدها")
async def handle_admin_purchases_menu(message: types.Message):
    """لیست خریدهای در انتظار تایید"""
    if not is_admin(message.from_user.id):
        return
    
    rows = await get_all_rows("Purchases")
    pending = [row for row in rows[1:] if row and len(row) > 8 and row[8] == "pending"]
    
    if not pending:
        await message.reply("✅ خریدی در انتظار تایید نیست.")
        return
    
    text = "💳 <b>خریدهای در انتظار تایید:</b>\n\n"
    for row in pending[:10]:  # فقط ۱۰ تا اول
        purchase_id = row[0] if len(row) > 0 else ""
        user_id = row[1] if len(row) > 1 else ""
        product = row[3] if len(row) > 3 else ""
        amount = row[4] if len(row) > 4 else "0"
        
        text += (
            f"🔢 <code>{purchase_id}</code>\n"
            f"👤 <code>{user_id}</code>\n"
            f"📦 {product} - ${amount}\n\n"
        )
    
    text += "\nبرای تایید/رد در Google Sheets اقدام کنید."
    
    await message.reply(text, parse_mode="HTML")


@dp.message_handler(lambda msg: msg.text == "💸 تایید برداشت‌ها")
async def handle_admin_withdrawals_menu(message: types.Message):
    """لیست برداشت‌های در انتظار"""
    if not is_admin(message.from_user.id):
        return
    
    rows = await get_all_rows("Withdrawals")
    pending = [row for row in rows[1:] if row and len(row) > 6 and row[6] == "pending"]
    
    if not pending:
        await message.reply("✅ برداشتی در انتظار نیست.")
        return
    
    text = "💸 <b>برداشت‌های در انتظار:</b>\n\n"
    for row in pending[:10]:
        wd_id = row[0] if len(row) > 0 else ""
        user_id = row[1] if len(row) > 1 else ""
        amount = row[2] if len(row) > 2 else "0"
        method = row[3] if len(row) > 3 else ""
        
        text += (
            f"🔢 <code>{wd_id}</code>\n"
            f"👤 <code>{user_id}</code>\n"
            f"💰 ${amount} - {method}\n\n"
        )
    
    text += "\nبرای پرداخت/رد در Google Sheets اقدام کنید."
    
    await message.reply(text, parse_mode="HTML")


@dp.message_handler(lambda msg: msg.text == "🎟 کدهای تخفیف")
async def handle_admin_discount_codes_menu(message: types.Message):
    """راهنمای کدهای تخفیف"""
    if not is_admin(message.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ ساخت کد", callback_data="admin_create_discount"),
        InlineKeyboardButton("📋 لیست کدها", callback_data="admin_list_discount")
    )
    
    await message.reply(
        "🎟 <b>مدیریت کدهای تخفیف</b>",
        parse_mode="HTML",
        reply_markup=kb
    )


@dp.callback_query_handler(lambda c: c.data == "admin_create_discount")
async def callback_create_discount(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    await callback.message.edit_text(
        "➕ <b>ساخت کد تخفیف</b>\n\n"
        "از دستور زیر استفاده کنید:\n\n"
        "<code>/createcode CODE PERCENT MAX_USES VALID_DAYS</code>\n\n"
        "مثال:\n"
        "<code>/createcode SUMMER20 20 100 30</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "admin_list_discount")
async def callback_list_discount(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    # استفاده از /listcodes موجود
    rows = await get_all_rows("DiscountCodes")
    
    if len(rows) <= 1:
        await callback.message.edit_text("📋 هیچ کد تخفیفی وجود ندارد.")
        await callback.answer()
        return
    
    text = "📋 <b>کدهای تخفیف:</b>\n\n"
    
    for row in rows[1:][:10]:  # ۱۰ تا اول
        if not row or len(row) < 8:
            continue
        
        code = row[0]
        discount = row[1]
        max_uses = int(row[2]) if row[2] else 0
        used = row[3]
        status = row[7]
        
        status_emoji = "✅" if status == "active" else "❌"
        
        text += (
            f"{status_emoji} <code>{code}</code> - {discount}%\n"
            f"   استفاده: {used}/{max_uses if max_uses > 0 else '∞'}\n\n"
        )
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


@dp.message_handler(lambda msg: msg.text == "🌟 کدهای بوست")
async def handle_admin_boost_codes_menu(message: types.Message):
    """راهنمای کدهای بوست"""
    if not is_admin(message.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ ساخت کد", callback_data="admin_create_boost"),
        InlineKeyboardButton("📋 لیست کدها", callback_data="admin_list_boost")
    )
    
    await message.reply(
        "🌟 <b>مدیریت کدهای بوست</b>",
        parse_mode="HTML",
        reply_markup=kb
    )


@dp.callback_query_handler(lambda c: c.data == "admin_create_boost")
async def callback_create_boost(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    await callback.message.edit_text(
        "➕ <b>ساخت کد بوست</b>\n\n"
        "از دستور زیر استفاده کنید:\n\n"
        "<code>/createboost CODE L1% L2% MAX_USES VALID_DAYS</code>\n\n"
        "مثال:\n"
        "<code>/createboost VIP15 15 20 5 90</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "admin_list_boost")
async def callback_list_boost(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    rows = await get_all_rows("BoostCodes")
    
    if len(rows) <= 1:
        await callback.message.edit_text("📋 هیچ کد بوستی وجود ندارد.")
        await callback.answer()
        return
    
    text = "📋 <b>کدهای بوست:</b>\n\n"
    
    for row in rows[1:][:10]:
        if not row or len(row) < 9:
            continue
        
        code = row[0]
        l1 = row[1]
        l2 = row[2]
        max_uses = int(row[3]) if row[3] else 0
        used = row[4] if len(row) > 4 else "0"
        status = row[8] if len(row) > 8 else ""
        
        status_emoji = "✅" if status == "active" else "❌"
        
        text += (
            f"{status_emoji} <code>{code}</code>\n"
            f"   📊 L1: {l1}% | L2: {l2}%\n"
            f"   👥 استفاده: {used}/{max_uses if max_uses > 0 else '∞'}\n\n"
        )
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


@dp.message_handler(lambda msg: msg.text == "👤 جستجوی کاربر")
async def handle_admin_user_search_menu(message: types.Message):
    """راهنمای جستجوی کاربر"""
    if not is_admin(message.from_user.id):
        return
    
    user_states[message.from_user.id] = {"state": "awaiting_user_search"}
    
    await message.reply(
        "👤 <b>جستجوی کاربر</b>\n\n"
        "ID تلگرام کاربر را وارد کنید:",
        parse_mode="HTML"
    )


@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_user_search")
async def handle_user_search_query(message: types.Message):
    """پردازش جستجوی کاربر"""
    if not is_admin(message.from_user.id):
        return
    
    user_states.pop(message.from_user.id, None)
    
    try:
        search_id = int(message.text.strip())
    except ValueError:
        await message.reply("❌ ID نامعتبر!")
        return
    
    result = await find_user(search_id)
    
    if not result:
        await message.reply(f"❌ کاربری با ID <code>{search_id}</code> یافت نشد.", parse_mode="HTML")
        return
    
    _, user_row = result
    
    username = user_row[1] if len(user_row) > 1 else ""
    full_name = user_row[2] if len(user_row) > 2 else ""
    email = user_row[3] if len(user_row) > 3 else ""
    referral_code = user_row[4] if len(user_row) > 4 else ""
    balance = user_row[6] if len(user_row) > 6 else "0"
    status = user_row[7] if len(user_row) > 7 else ""
    
    # چک اشتراک
    subscription = await get_active_subscription(search_id)
    sub_info = "❌ ندارد"
    if subscription:
        sub_type = subscription[2] if len(subscription) > 2 else ""
        expires = parse_iso(subscription[5]) if len(subscription) > 5 else None
        expires_str = expires.strftime("%Y/%m/%d") if expires else "نامشخص"
        sub_info = f"✅ {sub_type} تا {expires_str}"
    
    text = (
        f"👤 <b>اطلاعات کاربر</b>\n\n"
        f"🆔 ID: <code>{search_id}</code>\n"
        f"👤 نام: {full_name}\n"
        f"📱 یوزرنیم: @{username or 'ندارد'}\n"
        f"📧 ایمیل: {email or 'ندارد'}\n"
        f"🎁 کد معرف: <code>{referral_code}</code>\n"
        f"💰 موجودی: ${balance}\n"
        f"📊 وضعیت: {status}\n"
        f"📅 اشتراک: {sub_info}"
    )
    
    await message.reply(text, parse_mode="HTML")

@dp.message_handler(lambda msg: msg.text == "💱 قیمت تتر")
async def handle_admin_usdt_price(message: types.Message):
    """منوی مدیریت قیمت تتر"""
    if not is_admin(message.from_user.id):
        return
    
    current_price = await get_usdt_price_from_config()
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("✏️ تغییر قیمت", callback_data="admin_change_usdt"),
        InlineKeyboardButton("🔄 بروزرسانی از Nobitex", callback_data="admin_fetch_usdt")
    )
    
    await message.reply(
        f"💱 <b>مدیریت قیمت تتر</b>\n\n"
        f"💵 قیمت فعلی: <b>{current_price:,.0f}</b> تومان\n\n"
        f"📝 این قیمت برای محاسبه خرید کارت بانکی استفاده می‌شود.",
        parse_mode="HTML",
        reply_markup=kb
    )


@dp.callback_query_handler(lambda c: c.data == "admin_change_usdt")
async def callback_admin_change_usdt(callback: types.CallbackQuery):
    """درخواست تغییر قیمت"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    user_states[callback.from_user.id] = {"state": "awaiting_usdt_price"}
    
    current_price = await get_usdt_price_from_config()
    
    await callback.message.edit_text(
        f"💱 <b>تغییر قیمت تتر</b>\n\n"
        f"💵 قیمت فعلی: <b>{current_price:,.0f}</b> تومان\n\n"
        f"لطفاً قیمت جدید را به <b>تومان</b> وارد کنید:\n\n"
        f"مثال: <code>165000</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_usdt_price")
async def handle_usdt_price_input(message: types.Message):
    """دریافت قیمت جدید تتر"""
    if not is_admin(message.from_user.id):
        return
    
    user_states.pop(message.from_user.id, None)
    
    try:
        new_price = float(message.text.strip().replace(",", ""))
        
        if new_price <= 0:
            await message.reply("❌ قیمت نامعتبر!")
            return
        
        # ذخیره در Config
        success = await set_usdt_price_in_config(new_price)
        
        if success:
            await message.reply(
                f"✅ <b>قیمت تتر بروزرسانی شد!</b>\n\n"
                f"💵 قیمت جدید: <b>{new_price:,.0f}</b> تومان\n\n"
                f"💡 از این لحظه تمام خریدهای کارت بانکی با قیمت جدید محاسبه می‌شود.",
                parse_mode="HTML"
            )
        else:
            await message.reply("❌ خطا در بروزرسانی!")
            
    except ValueError:
        await message.reply("❌ لطفاً فقط عدد وارد کنید!\n\nمثال: <code>165000</code>", parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data == "admin_fetch_usdt")
async def callback_admin_fetch_usdt(callback: types.CallbackQuery):
    """دریافت خودکار از Nobitex"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ در حال دریافت از Nobitex...")
    
    try:
        async with ClientSession() as session:
            async with session.get("https://api.nobitex.ir/v2/orderbook/USDTIRT", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    asks = data.get("asks", [])
                    if asks and len(asks) > 0:
                        price_rial = float(asks[0][0])
                        price_toman = price_rial / 10
                        
                        # ذخیره
                        await set_usdt_price_in_config(price_toman)
                        
                        await callback.message.edit_text(
                            f"✅ <b>قیمت از Nobitex دریافت شد!</b>\n\n"
                            f"💵 قیمت جدید: <b>{price_toman:,.0f}</b> تومان\n\n"
                            f"💡 قیمت بروزرسانی و در Config ذخیره شد.",
                            parse_mode="HTML"
                        )
                        await callback.answer()
                        return
        
        await callback.message.edit_text("❌ خطا در دریافت از Nobitex!")
        await callback.answer()
        
    except Exception as e:
        logger.exception(f"Nobitex fetch error: {e}")
        await callback.message.edit_text(f"❌ خطا: {e}")
        await callback.answer()

@dp.message_handler(lambda msg: msg.text == "💎 افیلیت‌ها")
async def handle_admin_affiliates_menu(message: types.Message):
    """منوی مدیریت افیلیت‌ها (مخفی)"""
    if not is_admin(message.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ افزودن افیلیت", callback_data="aff_create"),
        InlineKeyboardButton("📋 لیست افیلیت‌ها", callback_data="aff_list")
    )
    kb.add(
        InlineKeyboardButton("✏️ ویرایش افیلیت", callback_data="aff_edit"),
        InlineKeyboardButton("❌ حذف افیلیت", callback_data="aff_delete")
    )
    
    await message.reply(
        "💎 <b>مدیریت افیلیت‌های عمیق</b>\n\n"
        "افیلیت‌ها از سطح ۳ به بعد پورسانت دریافت می‌کنند.\n"
        "این سیستم کاملاً مخفی است.\n\n"
        "📝 <b>راهنما:</b>\n"
        "• افزودن: <code>/makeaffiliate USER_ID DEPTH RATE</code>\n"
        "• ویرایش: <code>/updateaffiliate USER_ID DEPTH RATE</code>\n"
        "• لیست: دکمه پایین\n\n"
        "مثال:\n"
        "<code>/makeaffiliate 123456789 10 5</code>\n"
        "(سطح ۳ تا ۱۰، نرخ ۵%)",
        parse_mode="HTML",
        reply_markup=kb
    )


@dp.callback_query_handler(lambda c: c.data == "aff_create")
async def callback_aff_create(callback: types.CallbackQuery):
    """راهنمای ساخت افیلیت"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    await callback.message.edit_text(
        "➕ <b>افزودن افیلیت جدید</b>\n\n"
        "از دستور زیر استفاده کنید:\n\n"
        "<code>/makeaffiliate USER_ID MAX_DEPTH RATE_PERCENT</code>\n\n"
        "<b>پارامترها:</b>\n"
        "• USER_ID: شناسه تلگرام کاربر\n"
        "• MAX_DEPTH: حداکثر سطح (مثلاً ۱۰)\n"
        "• RATE_PERCENT: نرخ پورسانت برای سطح ۳+ (مثلاً ۵)\n\n"
        "<b>مثال:</b>\n"
        "<code>/makeaffiliate 123456789 10 5</code>\n\n"
        "این کاربر از سطح ۳ تا ۱۰ با نرخ ۵٪ پورسانت می‌گیرد.",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "aff_list")
async def callback_aff_list(callback: types.CallbackQuery):
    """لیست افیلیت‌ها"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    rows = await get_all_rows("Affiliates")
    
    if len(rows) <= 1:
        await callback.message.edit_text("📋 هیچ افیلیتی وجود ندارد.")
        await callback.answer()
        return
    
    text = "📋 <b>لیست افیلیت‌ها:</b>\n\n"
    
    for row in rows[1:]:
        if not row or len(row) < 6:
            continue
        
        telegram_id = row[0]
        username = row[1] if len(row) > 1 else ""
        full_name = row[2] if len(row) > 2 else ""
        max_depth = row[3] if len(row) > 3 else "?"
        rate = row[4] if len(row) > 4 else "?"
        status = row[5] if len(row) > 5 else ""
        
        status_emoji = "✅" if status == "active" else "❌"
        
        text += (
            f"{status_emoji} <b>{full_name}</b> (@{username or 'ندارد'})\n"
            f"   🆔 <code>{telegram_id}</code>\n"
            f"   📊 سطح ۳ تا {max_depth} | نرخ: {rate}%\n\n"
        )
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "aff_edit")
async def callback_aff_edit(callback: types.CallbackQuery):
    """راهنمای ویرایش"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    await callback.message.edit_text(
        "✏️ <b>ویرایش افیلیت</b>\n\n"
        "از دستور زیر استفاده کنید:\n\n"
        "<code>/updateaffiliate USER_ID MAX_DEPTH RATE_PERCENT</code>\n\n"
        "<b>مثال:</b>\n"
        "<code>/updateaffiliate 123456789 20 7</code>\n\n"
        "این تنظیمات افیلیت را آپدیت می‌کند:\n"
        "• سطح جدید: ۳ تا ۲۰\n"
        "• نرخ جدید: ۷%\n\n"
        "⚠️ فقط پورسانت‌های جدید تحت تأثیر قرار می‌گیرند.",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "aff_delete")
async def callback_aff_delete(callback: types.CallbackQuery):
    """راهنمای حذف"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️", show_alert=True)
        return
    
    await callback.message.edit_text(
        "❌ <b>حذف افیلیت</b>\n\n"
        "از دستور زیر استفاده کنید:\n\n"
        "<code>/removeaffiliate USER_ID</code>\n\n"
        "<b>مثال:</b>\n"
        "<code>/removeaffiliate 123456789</code>\n\n"
        "این افیلیت را غیرفعال می‌کند.\n"
        "پورسانت‌های قبلی تغییر نمی‌کند.",
        parse_mode="HTML"
    )
    await callback.answer()

# ============================================
# ADMIN COMMANDS
# ============================================
@dp.message_handler(commands=["reply"])
async def cmd_admin_reply(message: types.Message):
    """Admin reply to ticket"""
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("استفاده: /reply TICKET_ID پاسخ")
        return
    
    ticket_id = parts[1]
    response = parts[2]
    
    rows = await get_all_rows("Tickets")
    for idx, row in enumerate(rows[1:], start=2):
        if row and row[0] == ticket_id:
            user_id = int(row[1])
            row[7] = response
            row[8] = now_iso()
            row[5] = "closed"
            await update_row("Tickets", idx, row)
            
            try:
                await bot.send_message(
                    user_id,
                    f"📬 <b>پاسخ پشتیبانی</b>\n\n"
                    f"🔢 <code>{ticket_id}</code>\n\n"
                    f"💬 {response}",
                    parse_mode="HTML"
                )
                await message.reply("✅ پاسخ ارسال شد.")
            except Exception as e:
                await message.reply(f"❌ خطا: {e}")
            return
    
    await message.reply("❌ تیکت یافت نشد.")

@dp.message_handler(commands=["stats"])
async def cmd_admin_stats(message: types.Message):
    """Admin statistics"""
    if not is_admin(message.from_user.id):
        return
    
    users = await get_all_rows("Users")
    subs = await get_all_rows("Subscriptions")
    purchases = await get_all_rows("Purchases")
    
    total_users = len(users) - 1
    active_subs = sum(1 for row in subs[1:] if row and len(row) > 3 and row[3] == "active")
    total_revenue = sum(float(row[4]) for row in purchases[1:] if row and len(row) > 8 and row[8] == "approved")
    
    await message.reply(
        f"📊 <b>آمار</b>\n\n"
        f"👥 کاربران: {total_users}\n"
        f"✅ اشتراک فعال: {active_subs}\n"
        f"💰 درآمد: ${total_revenue:.2f}\n"
        f"🛒 خرید: {len(purchases) - 1}",
        parse_mode="HTML"
    )

# ============================================
# ADMIN MESSAGING SYSTEM - نسخه نهایی
# جای دادن: جایی که قبلاً /broadcast بود حذف کنید
# و این کل بلوک رو بجاش بذارید
# ============================================

# ─── دستور /msg — پیام به یه نفر خاص ───
@dp.message_handler(commands=["msg"])
async def cmd_admin_msg(message: types.Message):
    """Admin: پیام به یه کاربر خاص با ID"""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)

    if len(parts) < 3:
        await message.reply(
            "📝 <b>پیام به کاربر خاص</b>\n\n"
            "فرمت:\n"
            "<code>/msg USER_ID پیام شما</code>\n\n"
            "مثال:\n"
            "<code>/msg 123456789 سلام، حساب شما بررسی شد.</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.reply("❌ ID نامعتبر! فقط عدد وارد کنید.")
        return

    text = parts[2]

    # چک کاربر وجود داره یا نه
    target = await find_user(target_id)
    if not target:
        user_states[message.from_user.id] = {
            "state": "confirm_msg_unknown_user",
            "target_id": target_id,
            "text": text
        }
        await message.reply(
            f"⚠️ کاربری با ID <code>{target_id}</code> در سیستم پیدا نشد.\n\n"
            "میخواید بنوشته بشه؟ (بله / نه)",
            parse_mode="HTML"
        )
        return

    try:
        await bot.send_message(target_id, text, parse_mode="HTML")
        _, target_row = target
        target_name = target_row[2] if len(target_row) > 2 else "نامشخص"
        target_username = target_row[1] if len(target_row) > 1 else ""
        await message.reply(
            f"✅ <b>پیام ارسال شد</b>\n\n"
            f"👤 به: {target_name} (@{target_username or 'ندارد'})\n"
            f"🆔 ID: <code>{target_id}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.reply(f"❌ خطا در ارسال: {e}")


# ─── تایید پیام به کاربر ناشناس ───
@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "confirm_msg_unknown_user")
async def handle_confirm_msg_unknown(message: types.Message):
    """تایید ارسال پیام به کاربر ناشناس"""
    if not is_admin(message.from_user.id):
        return

    state = user_states.pop(message.from_user.id, {})
    target_id = state.get("target_id")
    text = state.get("text")

    if message.text.strip().lower() in ["بله", "آره", "yes", "y"]:
        try:
            await bot.send_message(target_id, text, parse_mode="HTML")
            await message.reply(f"✅ پیام به <code>{target_id}</code> ارسال شد.", parse_mode="HTML")
        except Exception as e:
            await message.reply(f"❌ خطا: {e}")
    else:
        await message.reply("❌ لغو شد.")


# ─── دستور /broadcast — پیام به کل کاربران (با تایید) ───
@dp.message_handler(commands=["broadcast"])
async def cmd_admin_broadcast(message: types.Message):
    """Admin broadcast to all users - با مرحله تایید"""
    if not is_admin(message.from_user.id):
        return

    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.reply(
            "📝 <b>پیام به کل کاربران</b>\n\n"
            "فرمت:\n"
            "<code>/broadcast پیام شما</code>\n\n"
            "پیام شما به <b>تمام</b> کاربران ارسال میشه.\n"
            "قبل از ارسال یه مرحله تایید داره.",
            parse_mode="HTML"
        )
        return

    users = await get_all_rows("Users")
    total = len(users) - 1

    user_states[message.from_user.id] = {
        "state": "confirm_broadcast",
        "text": text
    }

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ بله، بفرست", callback_data="confirm_broadcast_yes"),
        InlineKeyboardButton("❌ لغو", callback_data="confirm_broadcast_no")
    )

    await message.reply(
        f"⚠️ <b>تایید ارسال</b>\n\n"
        f"👥 تعداد کاربران: <b>{total}</b> نفر\n\n"
        f"📝 پیام:\n{text}\n\n"
        f"مطمئنید؟",
        parse_mode="HTML",
        reply_markup=kb
    )


@dp.callback_query_handler(lambda c: c.data == "confirm_broadcast_yes")
async def callback_confirm_broadcast(callback: types.CallbackQuery):
    """تایید و ارسال broadcast"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ شما ادمین نیستید!", show_alert=True)
        return

    state = user_states.pop(callback.from_user.id, {})
    text = state.get("text", "")

    if not text:
        await callback.answer("❌ پیام یافت نشد!", show_alert=True)
        return

    await callback.message.edit_text("⏳ <b>در حال ارسال به کل کاربران...</b>", parse_mode="HTML")

    users = await get_all_rows("Users")
    success = 0
    failed = 0
    failed_ids = []

    for row in users[1:]:
        if not row or not row[0]:
            continue
        try:
            await bot.send_message(int(row[0]), text, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
            failed_ids.append(row[0])

    report = (
        f"✅ <b>Broadcast تمام شد</b>\n\n"
        f"📤 ارسال شد: <b>{success}</b> نفر\n"
        f"❌ خطا: <b>{failed}</b> نفر\n"
    )
    if failed_ids and len(failed_ids) <= 10:
        report += f"\n🆔 خطا دار: {', '.join(failed_ids)}"

    await callback.message.edit_text(report, parse_mode="HTML")
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "confirm_broadcast_no")
async def callback_cancel_broadcast(callback: types.CallbackQuery):
    """لغو broadcast"""
    user_states.pop(callback.from_user.id, None)
    await callback.message.edit_text("❌ <b>لغو شد.</b>", parse_mode="HTML")
    await callback.answer()


# ─── دستور /msklist — پیام به گروه فیلتر شده ───
@dp.message_handler(commands=["msklist"])
async def cmd_admin_msklist(message: types.Message):
    """Admin: منوی پیام به گروه فیلتر شده"""
    if not is_admin(message.from_user.id):
        return

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("✅ فعال (اشتراک دارن)", callback_data="msklist_active"),
        InlineKeyboardButton("⏰ منقضی (اشتراک تموم شده)", callback_data="msklist_expired"),
        InlineKeyboardButton("🎁 معرف کرده (پورسانت گرفتن)", callback_data="msklist_referrers"),
        InlineKeyboardButton("🎟 هدیه خریده", callback_data="msklist_gift_buyers"),
        InlineKeyboardButton("🌟 بوست فعال", callback_data="msklist_boosted"),
        InlineKeyboardButton("📝 لیست دستی ID ها", callback_data="msklist_manual"),
    )

    await message.reply(
        "📋 <b>پیام به گروه</b>\n\n"
        "گروه مورد نظر رو انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )


# ─── تابع فیلتر کاربران ───
async def get_filtered_users(filter_type: str) -> list:
    """
    فیلتر کاربران بر اساس نوع انتخاب شده
    Returns: لیست telegram_id های فیلتر شده
    """
    users_rows = await get_all_rows("Users")
    subs_rows = await get_all_rows("Subscriptions")
    referrals_rows = await get_all_rows("Referrals")
    purchases_rows = await get_all_rows("Purchases")
    now = datetime.utcnow()

    filtered = []

    if filter_type == "active":
        # اشتراک فعال و غیر منقضی
        for row in subs_rows[1:]:
            if not row or len(row) < 6:
                continue
            if row[3] == "active":
                expires = parse_iso(row[5]) if len(row) > 5 else None
                if expires and expires > now:
                    filtered.append(row[0])

    elif filter_type == "expired":
        # قبلا sub داشتن ولی الان فعال نیستن
        active_ids = set()
        for row in subs_rows[1:]:
            if not row or len(row) < 6:
                continue
            if row[3] == "active":
                expires = parse_iso(row[5]) if len(row) > 5 else None
                if expires and expires > now:
                    active_ids.add(row[0])

        seen = set()
        for row in subs_rows[1:]:
            if not row or len(row) < 4:
                continue
            tid = row[0]
            if tid not in active_ids and tid not in seen:
                seen.add(tid)
                filtered.append(tid)

    elif filter_type == "referrers":
        # حداقل یه بار پورسانت گرفتن
        seen = set()
        for row in referrals_rows[1:]:
            if row and len(row) > 0 and row[0] and row[0] not in seen:
                seen.add(row[0])
                filtered.append(row[0])

    elif filter_type == "gift_buyers":
        # هدیه خریده و تایید شده
        seen = set()
        for row in purchases_rows[1:]:
            if not row or len(row) < 9:
                continue
            if row[3].startswith("gift_") and row[8] == "approved" and row[1] not in seen:
                seen.add(row[1])
                filtered.append(row[1])

    elif filter_type == "boosted":
        # بوست فعال (فیلد 10)
        for row in users_rows[1:]:
            if not row or len(row) < 11:
                continue
            if row[10] and row[10].startswith("boost:"):
                filtered.append(row[0])

    return filtered


# ─── Callback های فیلتر msklist ───
# نکته: lambda فیلتر میکنه confirm رو جدا نگیره
@dp.callback_query_handler(lambda c: c.data.startswith("msklist_") and c.data not in ("msklist_confirm_yes", "msklist_confirm_no"))
async def callback_msklist_filter(callback: types.CallbackQuery):
    """فیلتر انتخاب شده رو پردازش کن"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ شما ادمین نیستید!", show_alert=True)
        return

    filter_type = callback.data.replace("msklist_", "")

    # لیست دستی - state جدا
    if filter_type == "manual":
        user_states[callback.from_user.id] = {
            "state": "awaiting_manual_id_list"
        }
        await callback.message.edit_text(
            "📝 <b>لیست دستی ID ها</b>\n\n"
            "ID های کاربران رو وارد کنید، هر کدوم یه خط جدا:\n\n"
            "<code>123456789\n"
            "987654321\n"
            "111222333</code>",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # فیلتر خودکار
    filtered_ids = await get_filtered_users(filter_type)

    filter_names = {
        "active": "فعال (اشتراک دارن)",
        "expired": "منقضی",
        "referrers": "معرف کرده",
        "gift_buyers": "هدیه خریده",
        "boosted": "بوست فعال"
    }

    if not filtered_ids:
        await callback.message.edit_text(
            f"⚠️ هیچ کاربری در گروه <b>{filter_names.get(filter_type, filter_type)}</b> پیدا نشد.",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # state ذخیره
    user_states[callback.from_user.id] = {
        "state": "awaiting_msklist_text",
        "filter_type": filter_type,
        "filtered_ids": filtered_ids
    }

    await callback.message.edit_text(
        f"📋 <b>گروه: {filter_names.get(filter_type, filter_type)}</b>\n\n"
        f"👥 تعداد کاربران: <b>{len(filtered_ids)}</b> نفر\n\n"
        f"📝 حالا پیام خود را بنویسید:",
        parse_mode="HTML"
    )
    await callback.answer()


# ─── دریافت لیست دستی ID ها ───
@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_manual_id_list")
async def handle_manual_id_list(message: types.Message):
    """پارس لیست دستی ID ها"""
    if not is_admin(message.from_user.id):
        return

    lines = [line.strip() for line in message.text.strip().split("\n") if line.strip()]
    valid_ids = []
    invalid = []

    for line in lines:
        # فقط عدد خالص رو بگیر
        cleaned = line.split()[0] if line.split() else ""
        try:
            tid = int(cleaned)
            valid_ids.append(str(tid))
        except ValueError:
            invalid.append(line)

    if not valid_ids:
        await message.reply("❌ هیچ ID معتبری پیدا نشد.\n\nدوباره لیست رو بفرست.")
        return

    user_states[message.from_user.id] = {
        "state": "awaiting_msklist_text",
        "filter_type": "manual",
        "filtered_ids": valid_ids
    }

    invalid_msg = f"\n⚠️ نامعتبر و حذف شد: {', '.join(invalid)}" if invalid else ""

    await message.reply(
        f"✅ <b>{len(valid_ids)}</b> ID معتبر ثبت شد{invalid_msg}\n\n"
        f"📝 حالا پیام خود را بنویسید:",
        parse_mode="HTML"
    )


# ─── دریافت پیام و نشون دادن preview ───
@dp.message_handler(lambda msg: user_states.get(msg.from_user.id, {}).get("state") == "awaiting_msklist_text")
async def handle_msklist_text(message: types.Message):
    """دریافت پیام و نشون دادن preview با تایید"""
    if not is_admin(message.from_user.id):
        return

    state = user_states.get(message.from_user.id, {})
    filtered_ids = state.get("filtered_ids", [])
    filter_type = state.get("filter_type", "")
    text = message.text.strip()

    if not text:
        await message.reply("❌ پیام خالیه! دوباره بنویسید.")
        return

    # state رو به مرحله تایید بذاریم
    user_states[message.from_user.id] = {
        "state": "confirm_msklist",
        "filtered_ids": filtered_ids,
        "filter_type": filter_type,
        "text": text
    }

    filter_names = {
        "active": "فعال",
        "expired": "منقضی",
        "referrers": "معرف کرده",
        "gift_buyers": "هدیه خریده",
        "boosted": "بوست فعال",
        "manual": "لیست دستی"
    }

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ بله، بفرست", callback_data="msklist_confirm_yes"),
        InlineKeyboardButton("❌ لغو", callback_data="msklist_confirm_no")
    )

    await message.reply(
        f"⚠️ <b>تایید ارسال</b>\n\n"
        f"📋 گروه: <b>{filter_names.get(filter_type, filter_type)}</b>\n"
        f"👥 تعداد: <b>{len(filtered_ids)}</b> نفر\n\n"
        f"📝 پیام:\n{text}\n\n"
        f"مطمئنید؟",
        parse_mode="HTML",
        reply_markup=kb
    )


# ─── تایید و ارسال به گروه فیلتر شده ───
@dp.callback_query_handler(lambda c: c.data == "msklist_confirm_yes")
async def callback_msklist_send(callback: types.CallbackQuery):
    """ارسال پیام به گروه فیلتر شده"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ شما ادمین نیستید!", show_alert=True)
        return

    state = user_states.pop(callback.from_user.id, {})
    filtered_ids = state.get("filtered_ids", [])
    text = state.get("text", "")

    if not text or not filtered_ids:
        await callback.answer("❌ خطا! دوباره شروع کنید.", show_alert=True)
        return

    await callback.message.edit_text("⏳ <b>در حال ارسال...</b>", parse_mode="HTML")

    success = 0
    failed = 0
    failed_ids = []

    for tid in filtered_ids:
        try:
            await bot.send_message(int(tid), text, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            failed_ids.append(tid)
            logger.error(f"msklist send failed to {tid}: {e}")

    report = (
        f"✅ <b>ارسال تمام شد</b>\n\n"
        f"📤 ارسال شد: <b>{success}</b> نفر\n"
        f"❌ خطا: <b>{failed}</b> نفر\n"
    )
    if failed_ids and len(failed_ids) <= 15:
        report += f"\n🆔 خطا دار: {', '.join(failed_ids)}"

    await callback.message.edit_text(report, parse_mode="HTML")
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "msklist_confirm_no")
async def callback_msklist_cancel(callback: types.CallbackQuery):
    """لغو ارسال گروه"""
    user_states.pop(callback.from_user.id, None)
    await callback.message.edit_text("❌ <b>لغو شد.</b>", parse_mode="HTML")
    await callback.answer()

@dp.message_handler(commands=["createcode"])
async def cmd_create_discount_code(message: types.Message):
    """Admin: Create discount code"""
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    
    if len(parts) < 4:
        await message.reply(
            "❌ <b>استفاده نادرست!</b>\n\n"
            "فرمت صحیح:\n"
            "<code>/createcode CODE PERCENT MAX_USES VALID_DAYS</code>\n\n"
            "مثال:\n"
            "<code>/createcode SUMMER20 20 100 30</code>\n\n"
            "توضیحات:\n"
            "• CODE: کد تخفیف (مثلاً SUMMER20)\n"
            "• PERCENT: درصد تخفیف (۱-۱۰۰)\n"
            "• MAX_USES: حداکثر استفاده (۰ = نامحدود)\n"
            "• VALID_DAYS: اعتبار به روز",
            parse_mode="HTML"
        )
        return
    
    try:
        code = parts[1].upper()
        discount = int(parts[2])
        max_uses = int(parts[3])
        valid_days = int(parts[4]) if len(parts) > 4 else 30
        
        if not (1 <= discount <= 100):
            await message.reply("❌ درصد تخفیف باید بین ۱ تا ۱۰۰ باشد!")
            return
        
        if max_uses < 0:
            await message.reply("❌ تعداد استفاده نامعتبر!")
            return
        
        success = await create_discount_code(code, discount, max_uses, valid_days, message.from_user.id)
        
        if success:
            await message.reply(
                f"✅ <b>کد تخفیف ساخته شد!</b>\n\n"
                f"🎟 کد: <code>{code}</code>\n"
                f"💰 تخفیف: <b>{discount}%</b>\n"
                f"👥 حداکثر: {max_uses if max_uses > 0 else 'نامحدود'}\n"
                f"📅 اعتبار: {valid_days} روز",
                parse_mode="HTML"
            )
        else:
            await message.reply("❌ کد تکراری است!")
            
    except ValueError:
        await message.reply("❌ مقادیر نامعتبر! فقط عدد وارد کنید.")
    except Exception as e:
        await message.reply(f"❌ خطا: {e}")


@dp.message_handler(commands=["listcodes"])
async def cmd_list_discount_codes(message: types.Message):
    """Admin: List all discount codes"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        rows = await get_all_rows("DiscountCodes")
        
        if len(rows) <= 1:
            await message.reply("📋 هیچ کد تخفیفی وجود ندارد.")
            return
        
        text = "📋 <b>کدهای تخفیف:</b>\n\n"
        
        for row in rows[1:]:
            if not row or len(row) < 8:
                continue
            
            code = row[0]
            discount = row[1]
            max_uses = int(row[2]) if row[2] else 0
            used = row[3]
            valid_until = parse_iso(row[4])
            status = row[7]
            
            valid_str = valid_until.strftime("%Y/%m/%d") if valid_until else "نامشخص"
            status_emoji = "✅" if status == "active" else "❌"
            
            text += (
                f"{status_emoji} <code>{code}</code> - {discount}%\n"
                f"   استفاده: {used}/{max_uses if max_uses > 0 else '∞'} | تا {valid_str}\n\n"
            )
        
        await message.reply(text, parse_mode="HTML")
        
    except Exception as e:
        await message.reply(f"❌ خطا: {e}")

@dp.message_handler(commands=["dashboard"])
async def cmd_admin_dashboard(message: types.Message):
    """Admin: Comprehensive dashboard"""
    if not is_admin(message.from_user.id):
        return
    
    await message.reply("⏳ در حال محاسبه آمار...")
    
    stats = await calculate_dashboard_stats()
    
    if not stats:
        await message.reply("❌ خطا در محاسبه آمار.")
        return
    
    # ساخت پیام
    dashboard_text = (
        "📊 <b>داشبورد مدیریت</b>\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👥 <b>کاربران:</b>\n"
        f"   • کل: <b>{stats['users']['total']}</b> نفر\n"
        f"   • امروز: <b>+{stats['users']['today']}</b> نفر\n"
        f"   • هفته: <b>+{stats['users']['week']}</b> نفر\n\n"
        
        "📅 <b>اشتراک‌ها:</b>\n"
        f"   • فعال: <b>{stats['subscriptions']['active']}</b>\n"
        f"   • منقضی: <b>{stats['subscriptions']['expired']}</b>\n"
        f"   • معمولی: <b>{stats['subscriptions']['normal']}</b>\n"
        f"   • ویژه: <b>{stats['subscriptions']['premium']}</b>\n\n"
        
        "💰 <b>درآمد:</b>\n"
        f"   • کل: <b>${stats['revenue']['total']:.2f}</b>\n"
        f"   • امروز: <b>${stats['revenue']['today']:.2f}</b>\n"
        f"   • هفته: <b>${stats['revenue']['week']:.2f}</b>\n"
        f"   • میانگین هر خرید: <b>${stats['revenue']['avg_purchase']:.2f}</b>\n\n"
        
        "🛒 <b>سفارشات:</b>\n"
        f"   • تایید شده: <b>{stats['revenue']['approved']}</b>\n"
        f"   • در انتظار: <b>{stats['revenue']['pending']}</b>\n"
        f"   • رد شده: <b>{stats['revenue']['rejected']}</b>\n\n"
        
        "📈 <b>نرخ تبدیل:</b>\n"
        f"   • تست → خرید: <b>{stats['conversion']['test_to_purchase']:.1f}%</b>\n"
        f"   • معمولی → ویژه: <b>{stats['conversion']['normal_to_premium']:.1f}%</b>\n\n"
        
        "🎁 <b>معرفی:</b>\n"
        f"   • تعداد: <b>{stats['referrals']['total_count']}</b>\n"
        f"   • کل پورسانت: <b>${stats['referrals']['total_commissions']:.2f}</b>\n\n"
        
        "💸 <b>برداشت‌ها:</b>\n"
        f"   • پرداخت شده: <b>${stats['withdrawals']['total']:.2f}</b>\n"
        f"   • در انتظار: <b>{stats['withdrawals']['pending']}</b>\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 <b>بهترین عملکرد:</b>\n"
        f"   • روز: <b>{stats['revenue']['best_day']}</b>\n"
        f"   • ساعت: <b>{stats['revenue']['best_hour']}</b>\n"
    )
    
    await message.reply(dashboard_text, parse_mode="HTML")

@dp.message_handler(commands=["createboost"])
async def cmd_create_boost(message: types.Message):
    """Admin: Create secret boost code"""
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    
    if len(parts) < 4:
        await message.reply(
            "📝 <b>ساخت کد بوست پورسانت</b>\n\n"
            "فرمت:\n"
            "<code>/createboost CODE L1% L2% MAX_USES VALID_DAYS</code>\n\n"
            "مثال:\n"
            "<code>/createboost VIP15 15 20 5 90</code>\n\n"
            "توضیحات:\n"
            "• CODE: کد مخفی\n"
            "• L1%: درصد پورسانت سطح 1\n"
            "• L2%: درصد پورسانت سطح 2\n"
            "• MAX_USES: حداکثر استفاده (0 = نامحدود)\n"
            "• VALID_DAYS: اعتبار به روز (پیش‌فرض 365)",
            parse_mode="HTML"
        )
        return
    
    try:
        code = parts[1].upper()
        level1 = int(parts[2])
        level2 = int(parts[3])
        max_uses = int(parts[4]) if len(parts) > 4 else 0
        valid_days = int(parts[5]) if len(parts) > 5 else 365
        
        # validation
        if not (1 <= level1 <= 50):
            await message.reply("❌ سطح 1 باید بین ۱ تا ۵۰ باشد!")
            return
        if not (1 <= level2 <= 50):
            await message.reply("❌ سطح 2 باید بین ۱ تا ۵۰ باشد!")
            return
        
        success = await create_boost_code(code, level1, level2, max_uses, valid_days, message.from_user.id)
        
        if success:
            await message.reply(
                f"✅ <b>کد بوست ساخته شد!</b>\n\n"
                f"🎟 کد: <code>{code}</code>\n"
                f"📊 سطح 1: <b>{level1}%</b>\n"
                f"📊 سطح 2: <b>{level2}%</b>\n"
                f"👥 حداکثر استفاده: {max_uses if max_uses > 0 else 'نامحدود'}\n"
                f"📅 اعتبار: {valid_days} روز\n\n"
                f"💡 دستور فعال کردن برای کاربر:\n"
                f"<code>/redeem {code}</code>",
                parse_mode="HTML"
            )
        else:
            await message.reply("❌ کد تکراری است!")
    
    except ValueError:
        await message.reply("❌ مقادیر نامعتبر! فقط عدد وارد کنید.")


@dp.message_handler(commands=["listboosts"])
async def cmd_list_boosts(message: types.Message):
    """Admin: List all boost codes"""
    if not is_admin(message.from_user.id):
        return
    
    rows = await get_all_rows("BoostCodes")
    
    if len(rows) <= 1:
        await message.reply("📋 هیچ کد بوستی وجود ندارد.")
        return
    
    text = "📋 <b>کدهای بوست پورسانت:</b>\n\n"
    
    for row in rows[1:]:
        if not row or len(row) < 9:
            continue
        
        code = row[0]
        l1 = row[1]
        l2 = row[2]
        max_uses = int(row[3]) if row[3] else 0
        used = row[4] if len(row) > 4 else "0"
        valid_until = parse_iso(row[5]) if len(row) > 5 else None
        status = row[8] if len(row) > 8 else ""
        
        valid_str = valid_until.strftime("%Y/%m/%d") if valid_until else "نامشخص"
        status_emoji = "✅" if status == "active" else "❌"
        
        text += (
            f"{status_emoji} <code>{code}</code>\n"
            f"   📊 L1: {l1}% | L2: {l2}%\n"
            f"   👥 استفاده: {used}/{max_uses if max_uses > 0 else '∞'}\n"
            f"   📅 تا: {valid_str}\n\n"
        )
    
    await message.reply(text, parse_mode="HTML")


@dp.message_handler(commands=["makeaffiliate"])
async def cmd_make_affiliate(message: types.Message):
    """ساخت افیلیت جدید"""
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    
    if len(parts) < 4:
        await message.reply(
            "❌ <b>فرمت نادرست!</b>\n\n"
            "فرمت صحیح:\n"
            "<code>/makeaffiliate USER_ID MAX_DEPTH RATE_PERCENT</code>\n\n"
            "مثال:\n"
            "<code>/makeaffiliate 123456789 10 5</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        user_id = int(parts[1])
        max_depth = int(parts[2])
        rate_percent = float(parts[3])
        notes = " ".join(parts[4:]) if len(parts) > 4 else ""
        
        # Validation
        if max_depth < 3:
            await message.reply("❌ حداقل سطح باید ۳ باشد!")
            return
        
        if not (0 < rate_percent <= 50):
            await message.reply("❌ نرخ باید بین ۰ تا ۵۰ درصد باشد!")
            return
        
        # ساخت
        success = await create_affiliate(user_id, max_depth, rate_percent, message.from_user.id, notes)
        
        if success:
            # دریافت اطلاعات کاربر
            user_result = await find_user(user_id)
            username = ""
            full_name = ""
            
            if user_result:
                _, user_row = user_result
                username = user_row[1] if len(user_row) > 1 else ""
                full_name = user_row[2] if len(user_row) > 2 else ""
            
            await message.reply(
                f"✅ <b>افیلیت ساخته شد!</b>\n\n"
                f"👤 {full_name} (@{username or 'ندارد'})\n"
                f"🆔 <code>{user_id}</code>\n\n"
                f"📊 سطح: ۳ تا {max_depth}\n"
                f"💰 نرخ: {rate_percent}%\n\n"
                f"🔐 این کاربر از سطح ۳ به بعد تا سطح {max_depth} با نرخ {rate_percent}% پورسانت دریافت می‌کند.",
                parse_mode="HTML"
            )
            
            # نوتیف به افیلیت (مخفی)
            try:
                await bot.send_message(
                    user_id,
                    f"💎 <b>تبریک! شما افیلیت ویژه شدید!</b>\n\n"
                    f"از این لحظه از سطح ۳ تا {max_depth} با نرخ {rate_percent}% پورسانت دریافت می‌کنید.\n\n"
                    f"🔐 این اطلاعات محرمانه است و فقط به شما اعلام شده.",
                    parse_mode="HTML"
                )
            except:
                pass
        else:
            await message.reply("❌ خطا! احتمالاً این کاربر قبلاً افیلیت است.")
    
    except ValueError:
        await message.reply("❌ مقادیر نامعتبر! فقط عدد وارد کنید.")


@dp.message_handler(commands=["updateaffiliate"])
async def cmd_update_affiliate(message: types.Message):
    """آپدیت افیلیت"""
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    
    if len(parts) < 4:
        await message.reply(
            "❌ <b>فرمت نادرست!</b>\n\n"
            "فرمت صحیح:\n"
            "<code>/updateaffiliate USER_ID MAX_DEPTH RATE_PERCENT</code>\n\n"
            "مثال:\n"
            "<code>/updateaffiliate 123456789 20 7</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        user_id = int(parts[1])
        max_depth = int(parts[2])
        rate_percent = float(parts[3])
        
        success = await update_affiliate(user_id, max_depth, rate_percent)
        
        if success:
            await message.reply(
                f"✅ <b>افیلیت آپدیت شد!</b>\n\n"
                f"🆔 <code>{user_id}</code>\n"
                f"📊 سطح جدید: ۳ تا {max_depth}\n"
                f"💰 نرخ جدید: {rate_percent}%",
                parse_mode="HTML"
            )
            
            # نوتیف
            try:
                await bot.send_message(
                    user_id,
                    f"💎 <b>تنظیمات افیلیت شما آپدیت شد!</b>\n\n"
                    f"📊 سطح: ۳ تا {max_depth}\n"
                    f"💰 نرخ: {rate_percent}%",
                    parse_mode="HTML"
                )
            except:
                pass
        else:
            await message.reply("❌ افیلیت یافت نشد!")
    
    except ValueError:
        await message.reply("❌ مقادیر نامعتبر!")


@dp.message_handler(commands=["removeaffiliate"])
async def cmd_remove_affiliate(message: types.Message):
    """حذف/غیرفعال کردن افیلیت"""
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    
    if len(parts) < 2:
        await message.reply(
            "❌ <b>فرمت نادرست!</b>\n\n"
            "فرمت صحیح:\n"
            "<code>/removeaffiliate USER_ID</code>\n\n"
            "مثال:\n"
            "<code>/removeaffiliate 123456789</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        user_id = int(parts[1])
        
        success = await deactivate_affiliate(user_id)
        
        if success:
            await message.reply(
                f"✅ <b>افیلیت غیرفعال شد!</b>\n\n"
                f"🆔 <code>{user_id}</code>\n\n"
                f"این کاربر دیگر پورسانت سطح ۳+ دریافت نمی‌کند.",
                parse_mode="HTML"
            )
            
            # نوتیف
            try:
                await bot.send_message(
                    user_id,
                    "💎 وضعیت افیلیت شما تغییر کرد.\n"
                    "برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.",
                    parse_mode="HTML"
                )
            except:
                pass
        else:
            await message.reply("❌ افیلیت یافت نشد!")
    
    except ValueError:
        await message.reply("❌ ID نامعتبر!")


@dp.message_handler(commands=["listaffiliates"])
async def cmd_list_affiliates(message: types.Message):
    """لیست تمام افیلیت‌ها"""
    if not is_admin(message.from_user.id):
        return
    
    rows = await get_all_rows("Affiliates")
    
    if len(rows) <= 1:
        await message.reply("📋 هیچ افیلیتی وجود ندارد.")
        return
    
    text = "📋 <b>لیست کامل افیلیت‌ها:</b>\n\n"
    
    active_count = 0
    inactive_count = 0
    
    for row in rows[1:]:
        if not row or len(row) < 6:
            continue
        
        telegram_id = row[0]
        username = row[1] if len(row) > 1 else ""
        full_name = row[2] if len(row) > 2 else ""
        max_depth = row[3] if len(row) > 3 else "?"
        rate = row[4] if len(row) > 4 else "?"
        status = row[5] if len(row) > 5 else ""
        
        if status == "active":
            active_count += 1
            status_emoji = "✅"
        else:
            inactive_count += 1
            status_emoji = "❌"
        
        text += (
            f"{status_emoji} <b>{full_name}</b>\n"
            f"   @{username or 'ندارد'} | <code>{telegram_id}</code>\n"
            f"   📊 L3-{max_depth} | {rate}%\n\n"
        )
    
    text += f"\n📊 جمع: {active_count} فعال | {inactive_count} غیرفعال"
    
    await message.reply(text, parse_mode="HTML")

@dp.message_handler(commands=["reset"])
async def cmd_reset(message: types.Message):
    """پاک کردن state"""
    user_states.pop(message.from_user.id, None)
    await message.reply("✅ State پاک شد. الان /start بزن")


# ============================================
# CALLBACK HANDLERS
# ============================================
@dp.callback_query_handler(lambda c: c.data == "back_to_menu")
async def callback_back_to_menu(callback: types.CallbackQuery):
    """Back to menu"""
    await callback.message.delete()
    await bot.send_message(
        callback.from_user.id,
        "منوی اصلی:",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "back_to_buy")
async def callback_back_to_buy(callback: types.CallbackQuery):
    """Back to buy"""
    kb = subscription_keyboard()
    await callback.message.edit_text(
        "💎 <b>خرید اشتراک</b>\n\n"
        f"⭐️ معمولی: <b>${NORMAL_PRICE}</b>\n"
        f"💎 ویژه: <b>${PREMIUM_PRICE}</b>\n\n"
        f"انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

# ============================================
# AUTO-PROCESS PURCHASES & TICKETS
# ============================================
async def poll_sheets_auto_process():
    """Check Purchases and Tickets every 30 seconds - Simple Admin Mode"""
    await asyncio.sleep(10)
    logger.info("🔄 Polling started (Simple Admin Mode)")
    
    while True:
        try:
            # ============ Process Purchases ============
            rows = await get_all_rows("Purchases")
            
            if not rows or len(rows) <= 1:
                await asyncio.sleep(30)
                continue
            
            header = rows[0]
            
            # Find column indexes
            try:
                admin_action_idx = header.index("admin_action")
                status_idx = header.index("status")
                notes_idx = header.index("notes")
                purchase_id_idx = header.index("purchase_id")
                telegram_id_idx = header.index("telegram_id")
                username_idx = header.index("username")
                product_idx = header.index("product")
                amount_usd_idx = header.index("amount_usd")
                payment_method_idx = header.index("payment_method")
                approved_at_idx = header.index("approved_at")
                approved_by_idx = header.index("approved_by")
            except ValueError as e:
                logger.error(f"Missing column in Purchases: {e}")
                await asyncio.sleep(30)
                continue
            
            for idx, row in enumerate(rows[1:], start=2):
                if not row or len(row) <= admin_action_idx:
                    continue
                
                try:
                    admin_action = row[admin_action_idx].strip().lower() if len(row) > admin_action_idx else ""
                    status = row[status_idx].strip().lower() if len(row) > status_idx else ""
                    notes = row[notes_idx].strip().lower() if len(row) > notes_idx else ""
                    
                    # Skip if no action or already processed
                    if not admin_action or "processed" in notes:
                        continue
                    
                    purchase_id = row[purchase_id_idx] if len(row) > purchase_id_idx else ""
                    telegram_id = int(row[telegram_id_idx]) if len(row) > telegram_id_idx and row[telegram_id_idx] else 0
                    username = row[username_idx] if len(row) > username_idx else ""
                    product = row[product_idx] if len(row) > product_idx else ""
                    amount_usd = float(row[amount_usd_idx]) if len(row) > amount_usd_idx and row[amount_usd_idx] else 0
                    payment_method = row[payment_method_idx] if len(row) > payment_method_idx else ""
                    
                    if not telegram_id:
                        continue
                    
                    # Process APPROVE
                    if admin_action == "approve":
                        logger.info(f"✅ Auto-approving {purchase_id} for user {telegram_id}")
                        
                        # ✅ چک نوع خرید
                        is_reserve = product.startswith("reserve_")
                        is_complete = product.startswith("complete_")
                        is_gift = product.startswith("gift_")
                        
                        # ─────────────────────────────────────────────────────────
                        # حالت ۱: پیش‌پرداخت (رزرو)
                        # ─────────────────────────────────────────────────────────
                        if is_reserve:
                            actual_product = product.replace("reserve_", "")
                            
                            # ثبت رزرو
                            await set_user_reserve(telegram_id, actual_product, 2.0)
                            
                            # پیام به کاربر
                            product_name = "ویژه" if actual_product == "premium" else "معمولی"
                            total = PREMIUM_PRICE if actual_product == "premium" else NORMAL_PRICE
                            remaining = total - 2.0
                            
                            try:
                                await bot.send_message(
                                    telegram_id,
                                    f"✅ <b>پیش‌پرداخت تایید شد!</b>\n\n"
                                    f"🎉 جایگاه شما رزرو شد!\n\n"
                                    f"📦 محصول: اشتراک {product_name}\n"
                                    f"💵 پرداخت شده: <b>$2.00</b>\n"
                                    f"💰 باقیمانده: <b>${remaining:.2f}</b>\n\n"
                                    f"⚠️ برای فعال‌سازی کامل، باید مبلغ باقیمانده را پرداخت کنید.\n\n"
                                    f"💡 از منوی 💰 کیف پول → 💵 تکمیل پیش‌پرداخت استفاده کنید.",
                                    parse_mode="HTML",
                                    reply_markup=main_menu_keyboard()
                                )
                                logger.info(f"✅ Sent reserve confirmation to {telegram_id}")
                            except Exception as e:
                                logger.exception(f"Failed to send reserve: {e}")
                        
                        # ─────────────────────────────────────────────────────────
                        # حالت ۲: تکمیل پیش‌پرداخت
                        # ─────────────────────────────────────────────────────────
                        elif is_complete:
                            actual_product = product.replace("complete_", "")
                            
                            # دریافت رزرو
                            reserve = await get_user_reserve_status(telegram_id)
                            
                            if not reserve["has_reserve"]:
                                logger.error(f"Complete but no reserve for {telegram_id}")
                            else:
                                # فعال‌سازی
                                try:
                                    await activate_subscription(telegram_id, username, actual_product, payment_method)
                                    
                                    # محاسبه پورسانت با کل مبلغ
                                    total_paid = reserve["amount_paid"] + amount_usd
                                    await process_referral_commission(purchase_id, telegram_id, total_paid)
                                    
                                    # پاک رزرو
                                    await clear_user_reserve(telegram_id)
                                except Exception as e:
                                    logger.exception(f"Failed to activate completion: {e}")
                                
                                # پیام
                                try:
                                    result = await find_user(telegram_id)
                                    if result:
                                        _, user_row = result
                                        referral_code = user_row[4] if len(user_row) > 4 else ""
                                        
                                        kb_share = social_share_keyboard("ویژه" if actual_product == "premium" else "معمولی")
                                        
                                        await bot.send_message(
                                            telegram_id,
                                            f"🎉 <b>اشتراک فعال شد!</b>\n\n"
                                            f"✅ پرداخت تکمیل شد\n"
                                            f"📅 مدت: ۶ ماه\n\n"
                                            f"🎁 کد معرف:\n<code>{referral_code}</code>\n\n"
                                            f"💡 با دعوت دوستان پورسانت کسب کنید!\n\n"
                                            f"📢 این خبر را به اشتراک بگذارید:",
                                            parse_mode="HTML",
                                            reply_markup=kb_share
                                        )
                                        logger.info(f"✅ Sent completion to {telegram_id}")
                                except Exception as e:
                                    logger.exception(f"Failed to send completion: {e}")
                        
                        # ─────────────────────────────────────────────────────────
                        # حالت ۳: هدیه
                        # ─────────────────────────────────────────────────────────
                        elif is_gift:
                            actual_product = product.replace("gift_", "")
                            
                            # دریافت پیام هدیه
                            gift_message = ""
                            if telegram_id in user_states:
                                gift_message = user_states[telegram_id].get("gift_message", "")
                            
                            # ساخت گیفت
                            gift_code = await create_gift_card(actual_product, telegram_id, username, gift_message)
                            
                            if gift_code:
                                bot_username = (await bot.get_me()).username
                                gift_link = f"https://t.me/{bot_username}?start=gift_{gift_code}"
                                
                                try:
                                    await bot.send_message(
                                        telegram_id,
                                        f"🎁 <b>هدیه شما آماده شد!</b>\n\n"
                                        f"🔗 <b>لینک هدیه:</b>\n<code>{gift_link}</code>\n\n"
                                        f"💡 این لینک را برای دوست خود ارسال کنید.\n"
                                        f"او با کلیک روی لینک، اشتراک فعال می‌شود!",
                                        parse_mode="HTML",
                                        reply_markup=main_menu_keyboard()
                                    )
                                except:
                                    pass
                            
                            # حذف state
                            user_states.pop(telegram_id, None)
                        
                        # ─────────────────────────────────────────────────────────
                        # حالت ۴: خرید عادی
                        # ─────────────────────────────────────────────────────────
                        else:
                            try:
                                await activate_subscription(telegram_id, username, product, payment_method)
                                await process_referral_commission(purchase_id, telegram_id, amount_usd)
                            except Exception as e:
                                logger.exception(f"Failed to activate: {e}")
                            
                            try:
                                result = await find_user(telegram_id)
                                if result:
                                    _, user_row = result
                                    referral_code = user_row[4] if len(user_row) > 4 else ""
                                    
                                    kb_share = social_share_keyboard("ویژه" if product == "premium" else "معمولی")
                                    
                                    await bot.send_message(
                                        telegram_id,
                                        f"🎉 <b>پرداخت تایید شد!</b>\n\n"
                                        f"✅ اشتراک فعال شد\n"
                                        f"📅 مدت: ۶ ماه\n\n"
                                        f"🎁 کد معرف:\n<code>{referral_code}</code>\n\n"
                                        f"💡 با دعوت دوستان پورسانت کسب کنید!\n\n"
                                        f"📢 این خبر را به اشتراک بگذارید:",
                                        parse_mode="HTML",
                                        reply_markup=kb_share
                                    )
                                    logger.info(f"✅ Sent approval to {telegram_id}")
                            except:
                                pass
                        
                        # Auto-fill columns
                        row[admin_action_idx] = ""  # Clear action
                        row[status_idx] = "approved"
                        row[approved_at_idx] = now_iso()
                        row[approved_by_idx] = "admin"
                        row[notes_idx] = "auto_processed"
                        await update_row("Purchases", idx, row)

                    # Process REJECT
                    elif admin_action == "reject":
                        logger.info(f"❌ Auto-rejecting {purchase_id} for user {telegram_id}")
                        
                        try:
                            await bot.send_message(
                                telegram_id,
                                "❌ <b>سفارش رد شد</b>\n\n"
                                "با پشتیبانی تماس بگیرید.",
                                parse_mode="HTML",
                                reply_markup=main_menu_keyboard()
                            )
                            logger.info(f"✅ Sent rejection to {telegram_id}")
                        except Exception as e:
                            logger.exception(f"Failed to send rejection: {e}")
                        
                        # Auto-fill columns
                        row[admin_action_idx] = ""  # Clear action
                        row[status_idx] = "rejected"
                        row[approved_at_idx] = now_iso()
                        row[approved_by_idx] = "admin"
                        row[notes_idx] = "auto_processed"
                        await update_row("Purchases", idx, row)
                
                except Exception as e:
                    logger.exception(f"Error processing purchase row {idx}: {e}")


            # ============ Process Withdrawals ============
            withdrawal_rows = await get_all_rows("Withdrawals")
            
            if withdrawal_rows and len(withdrawal_rows) > 1:
                wd_header = withdrawal_rows[0]
                
                try:
                    wd_id_idx = wd_header.index("withdrawal_id")
                    wd_telegram_id_idx = wd_header.index("telegram_id")
                    wd_amount_idx = wd_header.index("amount_usd")
                    wd_method_idx = wd_header.index("method")
                    wd_wallet_idx = wd_header.index("wallet_address")
                    wd_status_idx = wd_header.index("status")
                    wd_notes_idx = wd_header.index("notes")
                    wd_processed_at_idx = wd_header.index("processed_at")
                except ValueError as e:
                    logger.error(f"Missing column in Withdrawals: {e}")
                    await asyncio.sleep(30)
                    continue
                
                for idx, row in enumerate(withdrawal_rows[1:], start=2):
                    if not row or len(row) <= wd_status_idx:
                        continue
                    
                    try:
                        status = row[wd_status_idx].strip().lower() if len(row) > wd_status_idx else ""
                        notes = row[wd_notes_idx].strip() if len(row) > wd_notes_idx else ""
                        processed_at = row[wd_processed_at_idx].strip() if len(row) > wd_processed_at_idx else ""
                        
                        # Skip if already processed or no processed_at
                        if "processed" in notes.lower() or not processed_at:
                            continue
                        
                        withdrawal_id = row[wd_id_idx] if len(row) > wd_id_idx else ""
                        telegram_id = int(row[wd_telegram_id_idx]) if len(row) > wd_telegram_id_idx and row[wd_telegram_id_idx] else 0
                        amount = float(row[wd_amount_idx]) if len(row) > wd_amount_idx and row[wd_amount_idx] else 0
                        method = row[wd_method_idx] if len(row) > wd_method_idx else ""
                        
                        if not telegram_id:
                            continue
                        
                        if status == "completed":
                            logger.info(f"💸 Processing withdrawal {withdrawal_id} from sheet")
                            
                            # Deduct balance
                            await update_user_balance(telegram_id, amount, add=False)
                            
                            # Extract TXID from notes
                            txid = notes if notes and not "processed" in notes.lower() else ""
                            txid_display = f"\n🔗 <b>TXID:</b> <code>{txid}</code>" if txid else ""
                            
                            try:
                                await bot.send_message(
                                    telegram_id,
                                    f"✅ <b>برداشت انجام شد!</b>\n\n"
                                    f"💰 ${amount}\n"
                                    f"🔢 <code>{withdrawal_id}</code>{txid_display}\n\n"
                                    f"مبلغ واریز شد.",
                                    parse_mode="HTML",
                                    reply_markup=main_menu_keyboard()
                                )
                            except:
                                pass
                            
                            # Mark as processed
                            row[wd_notes_idx] = notes + " [auto_processed]" if notes else "auto_processed"
                            await update_row("Withdrawals", idx, row)
                        
                        elif status == "rejected":
                            logger.info(f"❌ Processing rejection {withdrawal_id} from sheet")
                            
                            try:
                                await bot.send_message(
                                    telegram_id,
                                    f"❌ <b>درخواست برداشت رد شد</b>\n\n"
                                    f"🔢 <code>{withdrawal_id}</code>\n\n"
                                    f"با پشتیبانی تماس بگیرید.",
                                    parse_mode="HTML",
                                    reply_markup=main_menu_keyboard()
                                )
                            except:
                                pass
                            
                            # Mark as processed
                            row[wd_notes_idx] = notes + " [auto_processed]" if notes else "auto_processed"
                            await update_row("Withdrawals", idx, row)
                    
                    except Exception as e:
                        logger.exception(f"Error processing withdrawal row {idx}: {e}")


            
            # ============ Process Tickets ============
            ticket_rows = await get_all_rows("Tickets")
            
            if ticket_rows and len(ticket_rows) > 1:
                ticket_header = ticket_rows[0]
                
                try:
                    ticket_id_idx = ticket_header.index("ticket_id")
                    ticket_telegram_id_idx = ticket_header.index("telegram_id")
                    ticket_response_idx = ticket_header.index("response")
                    ticket_responded_at_idx = ticket_header.index("responded_at")
                    ticket_status_idx = ticket_header.index("status")
                except ValueError as e:
                    logger.error(f"Missing column in Tickets: {e}")
                    await asyncio.sleep(30)
                    continue
                
                for idx, row in enumerate(ticket_rows[1:], start=2):
                    if not row or len(row) <= ticket_response_idx:
                        continue
                    
                    try:
                        ticket_id = row[ticket_id_idx] if len(row) > ticket_id_idx else ""
                        telegram_id = int(row[ticket_telegram_id_idx]) if len(row) > ticket_telegram_id_idx and row[ticket_telegram_id_idx] else 0
                        response = row[ticket_response_idx].strip() if len(row) > ticket_response_idx else ""
                        responded_at = row[ticket_responded_at_idx].strip() if len(row) > ticket_responded_at_idx else ""
                        
                        if not telegram_id or not response:
                            continue
                        
                        # Check if already sent
                        if "[sent]" in response or responded_at:
                            continue
                        
                        # Send response
                        logger.info(f"📬 Sending ticket {ticket_id} to {telegram_id}")
                        
                        try:
                            await bot.send_message(
                                telegram_id,
                                f"📬 <b>پاسخ پشتیبانی</b>\n\n"
                                f"🔢 <code>{ticket_id}</code>\n\n"
                                f"💬 {response}",
                                parse_mode="HTML",
                                reply_markup=main_menu_keyboard()
                            )
                            
                            # Auto-fill columns
                            row[ticket_response_idx] = response + " [sent]"
                            row[ticket_responded_at_idx] = now_iso()
                            row[ticket_status_idx] = "closed"
                            await update_row("Tickets", idx, row)
                            logger.info(f"✅ Sent ticket response to {telegram_id}")
                        except Exception as e:
                            logger.exception(f"Failed to send ticket: {e}")
                    
                    except Exception as e:
                        logger.exception(f"Error processing ticket row {idx}: {e}")
            
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.exception(f"💥 poll_sheets error: {e}")
            await asyncio.sleep(60)



# ============================================
# STARTUP & MAIN
# ============================================
async def on_startup(dp):
    """On startup"""
    logger.info("🚀 Bot starting...")
    
    for sheet_name, table_name in TABLE_MAP.items():
        try:
            supabase_client.table(table_name).select("id").limit(1).execute()
            logger.info(f"✅ Table: {sheet_name}")
        except Exception as e:
            logger.error(f"❌ Table {sheet_name}: {e}")
    
    asyncio.create_task(rebuild_subscription_schedules())
    asyncio.create_task(poll_sheets_auto_process())
    asyncio.create_task(send_monthly_reports())
    
    logger.info("✅ Bot started!")


async def rebuild_subscription_schedules():
    """Rebuild subscription schedules"""
    try:
        await asyncio.sleep(5)
        rows = await get_all_rows("Subscriptions")
        now = datetime.utcnow()
        
        for row in rows[1:]:
            if not row or len(row) < 6:
                continue
            
            telegram_id = int(row[0])
            product = row[2] if len(row) > 2 else ""
            status = row[3] if len(row) > 3 else ""
            expires_str = row[5] if len(row) > 5 else ""
            
            if status != "active":
                continue
            
            expires = parse_iso(expires_str)
            if not expires:
                continue
            
            if expires <= now:
                channels = [PREMIUM_CHANNEL_ID, NORMAL_CHANNEL_ID] if product == "premium" else [NORMAL_CHANNEL_ID]
                for channel in channels:
                    if channel:
                        await remove_from_channel(channel, telegram_id)
                
                idx = rows.index(row) + 1
                row[3] = "expired"
                await update_row("Subscriptions", idx, row)
            else:
                delay = (expires - now).total_seconds()
                channels = [PREMIUM_CHANNEL_ID, NORMAL_CHANNEL_ID] if product == "premium" else [NORMAL_CHANNEL_ID]
                asyncio.create_task(schedule_expiry(telegram_id, channels, delay))
                logger.info(f"✅ Scheduled expiry for {telegram_id} in {delay/3600:.1f}h")
                asyncio.create_task(schedule_expiry_reminders(telegram_id, expires))
    except Exception as e:
        logger.exception(f"Rebuild schedules failed: {e}")

async def on_shutdown(dp):
    """On shutdown"""
    logger.info("🛑 Shutting down...")
    await bot.close()

async def start_health_server():
    """Start health check server"""
    app = web.Application()
    
    async def health(request):
        return web.Response(text="OK")
    
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"✅ Health server on port {PORT}")

# ============================================
# MAIN ENTRY POINT
# ============================================
if __name__ == "__main__":
    try:
        logger.info("=" * 50)
        logger.info("🤖 TELEGRAM SUBSCRIPTION BOT")
        logger.info("=" * 50)
        
        loop = asyncio.get_event_loop()
        loop.create_task(start_health_server())
        
        executor.start_polling(
            dp,
            skip_updates=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown
        )
    except KeyboardInterrupt:
        logger.info("⛔️ Stopped by user")
    except Exception as e:
        logger.exception(f"💥 Fatal error: {e}")
















































