import asyncio
import os
from datetime import datetime

from aiogram import types

from bot_instance import bot, dp, user_states
from config import TEST_CHANNEL_ID
from sheets import get_all_rows, append_row, update_row, find_user
from keyboards import main_menu_keyboard, admin_menu_keyboard, channel_membership_keyboard

from main import (
    is_admin,
    send_and_record,
    reply_and_record,
    transition_to_menu,
    now_iso,
    parse_iso,
    get_active_subscription,
    activate_subscription,
    redeem_gift_card,
    generate_referral_code,
    generate_purchase_id,
    is_valid_email,
    create_or_update_user,
    check_required_channels,
    check_membership_for_all_messages,
    check_reserve_block,
    create_invite_link,
    schedule_test_removal,
)


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
            await reply_and_record(
                message,
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
            await reply_and_record(
                message,
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
                trigger=message,
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
                trigger=message,
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
            trigger=message,
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
            trigger=message,
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
            trigger=message,
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
    
    await reply_and_record(
        message,
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
        await transition_to_menu(
            callback,
            "✅ <b>عضویت شما تایید شد!</b>\n\nاز منوی زیر استفاده کنید:",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )
    else:
        await callback.answer("❌ هنوز عضو نشده‌اید!", show_alert=True)
        kb = channel_membership_keyboard(missing)
        await callback.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "close_share")
async def callback_close_share(callback: types.CallbackQuery):
    """Close share window"""
    await transition_to_menu(callback, reply_markup=main_menu_keyboard())
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
        await reply_and_record(
            message,
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
        
        await reply_and_record(
            message,
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
        await reply_and_record(
            message,
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
    
    await send_and_record(
        user.id,
        "✅ <b>ایمیل ثبت شد!</b>\n\nاز منوی زیر استفاده کنید:",
        trigger=message,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )

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
        await reply_and_record(message, "❌ کانال تست در دسترس نیست.")
        return
    
    rows = await get_all_rows("Purchases")
    for row in rows[1:]:
        if row and str(row[1]) == str(user.id) and row[3] == "test":
            await reply_and_record(message, "⚠️ شما قبلاً از تست استفاده کرده‌اید.")
            return
    
    link = await create_invite_link(TEST_CHANNEL_ID, expire_minutes=5)
    
    if not link:
        await reply_and_record(message, "❌ خطا در ایجاد لینک.")
        return
    
    purchase_id = generate_purchase_id()
    await append_row("Purchases", [
        purchase_id, str(user.id), user.username or "",
        "test", "0", "0", "test", "test",
        "approved", now_iso(), now_iso(), "system", "5min test"
    ])
    
    await reply_and_record(
        message,
        "🎉 <b>لینک تست (۵ دقیقه):</b>\n\n"
        f"{link}\n\n"
        "⏰ بعد از ۵ دقیقه حذف می‌شوید.",
        parse_mode="HTML"
    )
    
    asyncio.create_task(schedule_test_removal(user.id, TEST_CHANNEL_ID))
