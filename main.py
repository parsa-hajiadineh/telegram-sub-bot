
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
from aiogram.dispatcher.middlewares import BaseMiddleware
import base64
from supabase import create_client, Client as SupabaseClient

from config import (
    logger,
    BOT_TOKEN, ADMIN_TELEGRAM_ID, ADMIN2_TELEGRAM_ID,
    SUPABASE_URL, SUPABASE_KEY,
    REQUIRED_CHANNELS, NORMAL_CHANNEL_ID, PREMIUM_CHANNEL_ID, TEST_CHANNEL_ID,
    NORMAL_PRICE, PREMIUM_PRICE,
    TETHER_WALLET, CARD_NUMBER, CARD_HOLDER,
    PORT,
    REQUIRED_CHANNELS_LIST,
    supabase_client,
    SHEET_DEFINITIONS, TABLE_MAP,
)

from sheets import get_all_rows, append_row, update_row, find_user
from bot_instance import bot, dp, user_states, _last_bot_messages

# ============================================
# MIDDLEWARE: Auto-clean user messages
# ============================================
class AutoCleanMiddleware(BaseMiddleware):
    """Track user messages; cleanup is handled by send_and_record / reply_and_record."""
    async def on_post_process_message(self, message: types.Message, results, data):
        pass

dp.middleware.setup(AutoCleanMiddleware())

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
            trigger=message,
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

async def cleanup_previous_screen(user_id: int, trigger: types.Message = None):
    """Delete prior bot screen and optional user trigger message."""
    prev_bot = _last_bot_messages.pop(user_id, None)
    if prev_bot:
        await safe_delete_message(user_id, prev_bot)

    if trigger:
        await safe_delete_message(user_id, trigger.message_id)


def record_screen(user_id: int, message_id: int):
    """Track an inline-edited message as the current bot screen."""
    _last_bot_messages[user_id] = message_id


async def send_and_record(user_id: int, text: str, trigger: types.Message = None, **kwargs):
    """Send a fresh bot message and replace the previous screen."""
    kwargs.pop("reply_to_message_id", None)
    try:
        await cleanup_previous_screen(user_id, trigger)
        msg = await bot.send_message(user_id, text, **kwargs)
        _last_bot_messages[user_id] = msg.message_id
        return msg
    except Exception as e:
        logger.exception(f"Failed to send message to {user_id}: {e}")
        return None


async def reply_and_record(message: types.Message, text: str, **kwargs):
    """Drop-in replacement for message.reply() — no reply_to, cleans chat."""
    kwargs.pop("reply_to_message_id", None)
    user_id = message.from_user.id
    try:
        await cleanup_previous_screen(user_id, trigger=message)
        msg = await bot.send_message(user_id, text, **kwargs)
        _last_bot_messages[user_id] = msg.message_id
        return msg
    except Exception as e:
        logger.exception(f"Failed to reply to {user_id}: {e}")
        return None


async def edit_screen(callback: types.CallbackQuery, text: str, **kwargs):
    """Edit inline message and keep it tracked as the current screen."""
    await callback.message.edit_text(text, **kwargs)
    record_screen(callback.from_user.id, callback.message.message_id)


async def transition_to_menu(callback: types.CallbackQuery, text: str = "از منوی زیر استفاده کنید:", **kwargs):
    """Remove inline screen and show reply-keyboard menu."""
    user_id = callback.from_user.id
    try:
        await callback.message.delete()
    except Exception:
        pass
    _last_bot_messages.pop(user_id, None)
    return await send_and_record(user_id, text, **kwargs)

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

from keyboards import (
    main_menu_keyboard,
    admin_menu_keyboard,
    subscription_keyboard,
    payment_method_keyboard,
    wallet_keyboard,
    withdrawal_method_keyboard,
    channel_membership_keyboard,
    admin_purchase_keyboard,
    admin_withdrawal_keyboard,
    social_share_keyboard,
)

from jobs import (
    schedule_expiry,
    schedule_expiry_reminders,
    generate_monthly_report,
    send_monthly_reports,
    schedule_test_removal,
    poll_sheets_auto_process,
    rebuild_subscription_schedules,
)


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
        message.from_user.id,
        f"⏳ <b>پیش‌پرداخت فعال</b>\n\n"
        f"شما رزرو انجام داده‌اید:\n"
        f"📦 محصول: اشتراک {product_name}\n"
        f"💵 پرداخت شده: <b>${paid:.2f}</b>\n"
        f"💰 باقیمانده: <b>${remaining:.2f}</b>\n\n"
        f"⚠️ برای استفاده از ربات، ابتدا باید پرداخت را تکمیل کنید.\n\n"
        f"💡 برای تکمیل، از منوی 💰 کیف پول → تکمیل پیش‌پرداخت استفاده کنید.",
        trigger=message,
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
            
            status = row[9] if len(row) > 9 else ""
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




import handlers.admin
import handlers.start
import handlers.subscription
import handlers.wallet
import handlers.support

# ============================================
# COMMAND HANDLERS
# ============================================














# ============================================
# WALLET SYSTEM
# ============================================






# ============================================
# REFERRAL SYSTEM
# ============================================






































# ============================================
# AUTO-PROCESS PURCHASES & TICKETS
# ============================================



# ============================================
# STARTUP & MAIN
# ============================================
async def on_startup(dp):
    """On startup"""
    logger.info("🚀 Bot starting...")

    user_states.load_all()
    
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
















































