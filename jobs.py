import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from config import (
    logger,
    PREMIUM_PRICE, NORMAL_PRICE,
    PREMIUM_CHANNEL_ID, NORMAL_CHANNEL_ID,
)
from sheets import get_all_rows, update_row, find_user
from keyboards import (
    main_menu_keyboard,
    subscription_keyboard,
    social_share_keyboard,
)


async def schedule_expiry(telegram_id: int, channels: List[str], delay: float):
    """Schedule subscription expiry"""
    from bot_instance import bot
    from main import remove_from_channel
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
    from bot_instance import bot
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
    from main import parse_iso
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
    from bot_instance import bot
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


async def schedule_test_removal(user_id: int, channel_id: str):
    """Schedule test removal"""
    from bot_instance import bot
    from main import remove_from_channel
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


async def poll_sheets_auto_process():
    """Check Purchases and Tickets every 30 seconds - Simple Admin Mode"""
    from bot_instance import bot, user_states
    from main import (
        now_iso,
        set_user_reserve, get_user_reserve_status,
        activate_subscription, process_referral_commission,
        clear_user_reserve, create_gift_card,
        update_user_balance,
    )
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


async def rebuild_subscription_schedules():
    """Rebuild subscription schedules"""
    from main import remove_from_channel, parse_iso
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
