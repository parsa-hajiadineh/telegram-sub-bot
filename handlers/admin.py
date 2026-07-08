import asyncio
from datetime import datetime

from aiohttp import ClientSession
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot_instance import bot, dp, user_states
from config import logger, ADMIN_TELEGRAM_ID, ADMIN2_TELEGRAM_ID
from sheets import get_all_rows, append_row, update_row, find_user
from keyboards import admin_menu_keyboard, main_menu_keyboard

from main import (
    is_admin,
    send_and_record,
    now_iso,
    parse_iso,
    get_usdt_price_from_config,
    set_usdt_price_in_config,
    get_active_subscription,
    create_discount_code,
    create_boost_code,
    create_affiliate,
    update_affiliate,
    deactivate_affiliate,
    calculate_dashboard_stats,
)


@dp.message_handler(lambda msg: msg.text == "🔐 پنل ادمین")
async def handle_go_to_admin_panel(message: types.Message):
    """رفتن به پنل ادمین از منوی عادی"""
    if not is_admin(message.from_user.id):
        return

    await send_and_record(
        message.from_user.id,
        "🔐 <b>پنل ادمین</b>",
        parse_mode="HTML",
        reply_markup=admin_menu_keyboard()
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

@dp.message_handler(lambda msg: msg.text == "🔙 منوی عادی")
async def handle_back_to_user_menu(message: types.Message):
    """برگشت از منوی ادمین به منوی کاربر عادی"""
    if not is_admin(message.from_user.id):
        return

    await send_and_record(
        message.from_user.id,
        "🔄 بازگشت به منوی کاربر",
        reply_markup=main_menu_keyboard(show_admin_btn=True)
    )


@dp.message_handler(commands=["reset"])
async def cmd_reset(message: types.Message):
    """پاک کردن state"""
    user_states.pop(message.from_user.id, None)
    await message.reply("✅ State پاک شد. الان /start بزن")
