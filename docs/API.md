# API.md — Bot Interface & External APIs

## Telegram Bot Interface

### User Commands
| Command | Parameters | Description |
|---------|-----------|-------------|
| `/start` | Optional: `CODE` (referral/gift deep link) | Entry point; registers user, handles referral & gift card links |
| `/redeem CODE` | `CODE` = boost code | Secret boost activation for users |

### Admin Commands
| Command | Parameters | Description |
|---------|-----------|-------------|
| `/amiadmin` | — | Debug: prints admin status |
| `/stats` | — | Quick system statistics |
| `/dashboard` | — | Full admin dashboard with metrics |
| `/reply TICKET_ID TEXT` | ticket ID + reply text | Reply to a support ticket |
| `/msg USER_ID TEXT` | user ID + message text | Send a direct message to a user |
| `/broadcast TEXT` | message text | Broadcast to all users (with confirmation step) |
| `/msklist` | — | Filtered group messaging |
| `/createcode CODE PERCENT MAX_USES VALID_UNTIL` | — | Create discount code |
| `/listcodes` | — | List all discount codes |
| `/createboost CODE L1% L2% MAX_USES VALID_UNTIL` | — | Create boost code |
| `/listboosts` | — | List all boost codes |
| `/makeaffiliate USER_ID MAX_DEPTH RATE%` | — | Grant affiliate status |
| `/updateaffiliate USER_ID FIELD VALUE` | — | Update affiliate settings |
| `/removeaffiliate USER_ID` | — | Remove affiliate status |
| `/listaffiliates` | — | List all affiliates |
| `/reset` | — | Clear own user state (debug) |
| `/report` | — | User monthly report |

### Deep Link Formats
| Format | Purpose |
|--------|---------|
| `t.me/BOT?start=REF_CODE` | Referral link — credits referrer on new registration |
| `t.me/BOT?start=gift_GIFTCODE` | Gift card redemption link |

### Reply Keyboard Menus

**User Main Menu:**
- My Subscription
- Buy Subscription
- Wallet
- Referral Program
- Support
- Profile

**Admin Menu (additional buttons when `is_admin`):**
- System Stats
- Pending Purchases
- Pending Withdrawals
- Broadcast
- Discount Codes
- Boost Codes
- User Search
- Set USDT Price
- Affiliates

### Inline Callback Actions
Callback data patterns used throughout the bot:

| Pattern | Description |
|---------|-------------|
| `buy_normal` / `buy_premium` | Initiate subscription purchase |
| `pay_usdt` / `pay_card` / `pay_wallet` | Select payment method |
| `approve_purchase_ID` | Admin approves a purchase |
| `reject_purchase_ID` | Admin rejects a purchase |
| `approve_withdrawal_ID` | Admin approves a withdrawal |
| `reject_withdrawal_ID` | Admin rejects a withdrawal |
| `confirm_broadcast` | Admin confirms broadcast send |
| `cancel_broadcast` | Admin cancels broadcast |
| `apply_discount` | Apply discount code at checkout |
| `skip_discount` | Skip discount code step |
| `buy_test` | Start free 5-minute test |
| `create_gift_normal` / `create_gift_premium` | Create gift card |
| `redeem_gift_CODE` | Redeem a gift card |
| `withdraw_usdt` / `withdraw_card` | Choose withdrawal method |
| `confirm_withdrawal` | Confirm withdrawal request |
| `reserve_normal` / `reserve_premium` | Start pre-payment reserve flow |
| `complete_reserve` | Complete partial reserve payment |

---

## External APIs

### Telegram Bot API
- **Mode:** Long-polling (`executor.start_polling`)
- **Library:** aiogram 2.25.1
- **Permissions required on target channels:** Admin (to create invite links and ban/unban users)

**Key operations:**
- `bot.send_message(chat_id, text)` — send messages
- `bot.send_photo(chat_id, photo)` — send receipt photos
- `bot.create_chat_invite_link(chat_id, expire_date, member_limit)` — generate invite links
- `bot.ban_chat_member(chat_id, user_id)` / `bot.unban_chat_member(chat_id, user_id)` — remove/restore channel access
- `bot.get_chat_member(chat_id, user_id)` — verify membership status

---

### Google Sheets API
- **Library:** gspread 6.0.0 + google-auth 2.25.2
- **Auth:** Service account JSON (`GOOGLE_CREDENTIALS` env var or `service-account.json` file)
- **Scope:** `https://spreadsheets.google.com/feeds`, `https://www.googleapis.com/auth/drive`
- **Access:** The spreadsheet must be shared with the service account email

**Operations used:**
- Open spreadsheet by ID
- List worksheets
- Add worksheet with header row
- Get all values as list of dicts
- Append row
- Update row by index
- Find cell by value

---

### Nobitex REST API
- **Purpose:** Fetch live USDT/IRR exchange rate
- **Endpoint:** `GET https://api.nobitex.ir/v2/orderbook/USDTIRT`
- **Field used:** `lastTradePrice` from response
- **Fallback:** 160,000 Toman if request fails or rate is unavailable
- **Override:** Admin can set `usdt_price_irr` key in the `Config` sheet to bypass live fetch

---

## Health Check Endpoint
- **Server:** aiohttp
- **Port:** `$PORT` (default `8000`)
- **Routes:**
  - `GET /` → `200 OK` with body `"OK"`
  - `GET /health` → `200 OK` with body `"OK"`
- **Purpose:** Render platform health monitoring to keep service alive
