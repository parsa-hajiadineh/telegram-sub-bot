# ARCHITECTURE.md — System Architecture

## Overview
Single-process Python application. All logic is contained in `main.py` (~6,630 lines). No microservices, no separate modules, no ORM.

## Component Diagram
```
┌─────────────────────────────────────────────────────┐
│                    main.py                          │
│                                                     │
│  ┌──────────────┐   ┌──────────────────────────┐   │
│  │ aiogram Bot  │   │ aiohttp Health Server    │   │
│  │ (Polling)    │   │ GET / → "OK"             │   │
│  └──────┬───────┘   └──────────────────────────┘   │
│         │                                           │
│  ┌──────▼───────────────────────────────────────┐  │
│  │           Handler Layer (70+ handlers)        │  │
│  │  @dp.message_handler / @dp.callback_handler  │  │
│  └──────┬───────────────────────────────────────┘  │
│         │                                           │
│  ┌──────▼──────────────┐  ┌──────────────────────┐ │
│  │  Business Logic     │  │  Background Jobs     │ │
│  │  (inline in main)   │  │  (asyncio tasks)     │ │
│  └──────┬──────────────┘  └──────────────────────┘ │
│         │                                           │
│  ┌──────▼───────────────┐                          │
│  │  Google Sheets Layer │                          │
│  │  (gspread + cache)   │                          │
│  └──────────────────────┘                          │
└─────────────────────────────────────────────────────┘
         │                           │
         ▼                           ▼
  Telegram API               Google Sheets API
  (Bot API polling)          (Service Account)
         │
         ▼
  Nobitex REST API
  (USDT/IRR rate)
```

## Layers

### 1. Configuration Layer (lines ~1–100)
- Reads all `os.getenv` values at startup
- Validates required vars (`BOT_TOKEN`, `SPREADSHEET_ID`)
- Defines `SHEET_DEFINITIONS` (sheet names + headers)
- Defines `ADMIN_IDS` set

### 2. Google Sheets Abstraction (lines ~100–400)
- `open_spreadsheet()` — authenticates and opens sheet; 60-second cache
- `get_worksheet(name)` — auto-creates sheet with headers if missing
- `get_all_rows(sheet)` — returns list of dicts (header-keyed)
- `append_row(sheet, data)` — appends dict as row
- `update_row(sheet, row_idx, data)` — updates existing row
- `find_user(telegram_id)` — finds user row by ID

### 3. User & Business Logic (lines ~400–824)
- User create/update, balance management
- Subscription activation, expiry scheduling
- Referral commission calculation
- Affiliate deep-commission logic
- Discount code, boost code, gift card helpers
- Nobitex price fetch with fallback (160,000 Toman)

### 4. Keyboard Builders (lines ~824–1100)
- All `InlineKeyboardMarkup` and `ReplyKeyboardMarkup` builders
- User main menu, admin menu, payment flows, confirmation prompts

### 5. Message Handlers (lines ~1100–4000)
- `/start` (new user, referral, gift card, deep link flows)
- Registration (email capture with confirmation)
- Main menu navigation
- Subscription purchase flows (Normal, Premium, Test)
- Pre-payment reserve flow
- Wallet and withdrawal flow
- Gift card creation/redemption
- Discount code application
- Support ticket creation/reply
- All admin commands and inline approval callbacks

### 6. Admin System (lines ~4000–5500)
- Stats dashboard (`calculate_dashboard_stats`)
- Broadcast messaging
- Purchase approval (inline buttons + sheet-driven)
- Withdrawal approval
- Discount/boost code management
- User search
- USDT price override
- Affiliate management

### 7. Background Jobs (lines ~5500–6200)
- `poll_sheets_auto_process` (every 30s) — processes sheet-set `admin_action` values
- `schedule_expiry` — removes expired users from channels
- `schedule_expiry_reminders` — sends reminders at 7d, 3d, 1d before expiry
- `send_monthly_reports` — fires on 1st of month at 10:00 UTC
- `schedule_test_removal` — removes test users after 5 minutes
- `rebuild_subscription_schedules` — restores timers on restart

### 8. Startup / Entry Point (lines ~6200–6630)
- `on_startup(dp)` — initializes sheets, rebuilds schedules, starts background tasks
- `executor.start_polling(dp, on_startup=on_startup)` — starts bot

## State Management
- **User state** stored in-process `dict` keyed by `telegram_id`
- State keys include: `step`, `email`, `payment_method`, `product`, `gift_code`, `ticket_subject`, etc.
- State is **lost on restart** — no persistence for in-progress flows

## Caching
- Google Sheets client: 60-second TTL (`_sheet_cache`, `_sheet_cache_time`)
- No other caching layer

## Concurrency
- Single `asyncio` event loop
- All I/O is non-blocking (aiogram, aiohttp, gspread async wrappers)
- Background tasks run as `asyncio.create_task`

## External Services
| Service | Protocol | Purpose |
|---------|----------|---------|
| Telegram Bot API | HTTPS polling | Bot messaging |
| Google Sheets API | HTTPS REST | All data storage |
| Nobitex REST API | HTTPS GET | USDT/IRR exchange rate |

## Known Structural Issues
1. **Monolithic file** — 6,630 lines in one file (originally 3 concatenated parts)
2. **In-memory state** — lost on restart; mid-flow users lose progress
3. **`INSTANCE_MODE`** env var defined but never used; webhook not implemented
4. **Line 1080 typo** — `massage.from_user.id` instead of `message.from_user.id` in `check_reserve_block`
5. **Column index inconsistency** — some code uses index 8, some 9 for `status` in Purchases sheet
6. **No `.gitignore`** — risk of accidentally committing `service-account.json`
