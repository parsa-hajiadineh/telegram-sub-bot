import urllib.parse

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot_instance import bot, dp, user_states
from config import logger, ADMIN_TELEGRAM_ID, NORMAL_PRICE, PREMIUM_PRICE
from sheets import get_all_rows, append_row, find_user
from keyboards import main_menu_keyboard, subscription_keyboard
from jobs import generate_monthly_report

from main import (
    check_membership_for_all_messages,
    check_reserve_block,
    send_and_record,
    reply_and_record,
    transition_to_menu,
    record_screen,
    now_iso,
    generate_ticket_id,
    get_user_boost,
    validate_and_apply_boost,
)


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
        await reply_and_record(message,
            "⚠️ <b>برای استفاده از سیستم معرفی، ابتدا باید اشتراک خریداری کنید.</b>\n\n"
            "پس از خرید و تایید، کد معرف فعال می‌شود.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )
        return
    
    result = await find_user(user.id)
    
    if not result:
        await reply_and_record(message, "❌ خطا در بارگذاری اطلاعات.", reply_markup=main_menu_keyboard())
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
    
    await reply_and_record(message,
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
    
    await reply_and_record(message,
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
    
    await reply_and_record(message,
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
    
    await reply_and_record(message,
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
        await reply_and_record(message, report, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else:
        await reply_and_record(message,
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
        await reply_and_record(message,
            "✅ <b>شما قبلاً یک آفر ویژه فعال دارید!</b>",
            parse_mode="HTML"
        )
        return
    
    # موفق شد
    await reply_and_record(message,
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


# ============================================
# CALLBACK HANDLERS
# ============================================
@dp.callback_query_handler(lambda c: c.data == "back_to_menu")
async def callback_back_to_menu(callback: types.CallbackQuery):
    """Back to menu"""
    await transition_to_menu(callback, reply_markup=main_menu_keyboard())
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
    record_screen(callback.from_user.id, callback.message.message_id)
    await callback.answer()
