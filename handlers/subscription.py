import os

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot_instance import bot, dp, user_states
from config import (
    logger,
    NORMAL_PRICE, PREMIUM_PRICE,
    TETHER_WALLET, CARD_NUMBER, CARD_HOLDER,
    ADMIN_TELEGRAM_ID,
)
from sheets import get_all_rows, append_row, update_row, find_user
from keyboards import (
    main_menu_keyboard,
    subscription_keyboard,
    payment_method_keyboard,
    admin_purchase_keyboard,
    social_share_keyboard,
)

from main import (
    is_admin,
    send_and_record,
    reply_and_record,
    record_screen,
    now_iso,
    generate_purchase_id,
    check_membership_for_all_messages,
    check_reserve_block,
    get_user_reserve_status,
    set_user_reserve,
    clear_user_reserve,
    activate_subscription,
    validate_discount_code,
    get_usdt_price_irr,
    process_referral_commission,
    create_gift_card,
)


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
        trigger=message,
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
    record_screen(callback.from_user.id, callback.message.message_id)
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
        
        await reply_and_record(message,
            f"✅ <b>کد تخفیف معتبر!</b>\n\n"
            f"🎟 کد: <code>{code}</code>\n"
            f"💰 تخفیف: <b>{discount_percent}%</b>\n\n"
            f"حالا اشتراک مورد نظر را انتخاب کنید:",
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )
    else:
        user_states.pop(user.id, None)
        
        await reply_and_record(message,
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
    
    await reply_and_record(message,
        f"💳 <b>پرداخت هدیه</b>\n\n"
        f"💰 مبلغ: <b>${price_usd}</b>\n"
        f"🎁 نوع: {'معمولی' if product == 'normal' else 'ویژه'}\n"
        f"💬 پیام: {gift_message if gift_message else '(بدون پیام)'}\n\n"
        "روش پرداخت را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=kb
    )


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
        record_screen(user.id, callback.message.message_id)
    
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
        record_screen(user.id, callback.message.message_id)
    
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
        await reply_and_record(message, "❌ خطا: سفارش یافت نشد.")
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
    
    await reply_and_record(message,
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
        await reply_and_record(message, "❌ سفارش یافت نشد.")
        return
    
    if len(txid) < 20:
        await reply_and_record(message, "❌ TXID نامعتبر!")
        return
    
    rows = await get_all_rows("Purchases")
    for idx, row in enumerate(rows[1:], start=2):
        if row and row[0] == purchase_id:
            row[7] = txid
            row[9] = "pending"
            await update_row("Purchases", idx, row)
            break
    
    user_states.pop(user.id, None)
    
    await reply_and_record(message,
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
