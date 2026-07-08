import os
from typing import List

from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

from config import NORMAL_PRICE, PREMIUM_PRICE


# ============================================
# KEYBOARDS
# ============================================
def main_menu_keyboard(show_admin_btn: bool = False):
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
    if show_admin_btn:
        kb.row(KeyboardButton("🔐 پنل ادمین"))
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
