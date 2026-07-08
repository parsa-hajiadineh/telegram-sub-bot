
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
    PORT, INSTANCE_MODE,
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
    """پاک‌سازی خودکار پیام‌های دکمه‌ای کاربر برای خلوت ماندن چت"""
    async def on_post_process_message(self, message: types.Message, results, data):
        if not message.text or message.text.startswith('/'):
            return
        # اگه کاربر در حال وارد کردن اطلاعات است، پاک نکن
        if message.from_user.id in user_states:
            return
        try:
            await message.delete()
        except Exception:
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




import handlers.admin

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
















































