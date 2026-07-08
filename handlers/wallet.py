from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot_instance import bot, dp, user_states
from config import logger, NORMAL_PRICE, PREMIUM_PRICE, ADMIN_TELEGRAM_ID
from sheets import get_all_rows, append_row, update_row
from keyboards import (
    main_menu_keyboard,
    wallet_keyboard,
    payment_method_keyboard,
    withdrawal_method_keyboard,
)

from main import (
    is_admin,
    send_and_record,
    reply_and_record,
    now_iso,
    parse_iso,
    get_user_balance,
    update_user_balance,
    get_user_reserve_status,
    generate_withdrawal_id,
    check_membership_for_all_messages,
)


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
        trigger=message,
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
        await reply_and_record(message,
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
        await reply_and_record(message, "❌ مبلغ نامعتبر!")
        return
    
    if amount < 10:
        await reply_and_record(message, "❌ حداقل برداشت $10 است!")
        return
    
    if amount > balance:
        await reply_and_record(message, f"❌ موجودی کافی نیست! موجودی شما: ${balance:.2f}")
        return
    
    destination = parts[1]
    
    # Validate destination format
    if method == "usdt":
        if not destination.startswith("0x") or len(destination) < 20:
            await reply_and_record(message,
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
    
    await reply_and_record(message,
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
        await reply_and_record(message, "❌ TXID نامعتبر است. لطفاً TXID صحیح را ارسال کنید.")
        return
    
    # Process approval
    await process_withdrawal_approval(
        withdrawal_id, withdrawal_idx, user_id, 
        amount, "usdt", destination, txid
    )
    
    user_states.pop(message.from_user.id, None)
    
    await reply_and_record(message,
        f"✅ <b>برداشت تایید و پردازش شد</b>\n\n"
        f"💰 مبلغ: ${amount}\n"
        f"🔗 TXID: <code>{txid}</code>\n\n"
        f"کاربر مطلع شد.",
        parse_mode="HTML"
    )
