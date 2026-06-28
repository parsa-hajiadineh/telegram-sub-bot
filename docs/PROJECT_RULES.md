# PROJECT_RULES.md — Development Rules & Conventions

## Code Rules

### Language & Style
- Language: **Python 3.11**
- All code in a **single file** (`main.py`) — do not split into modules unless explicitly requested
- Persian comments are acceptable (existing codebase uses Persian)
- No type hints currently — do not add unless explicitly requested
- No external linter config — follow PEP 8 informally

### Naming Conventions
- Functions: `snake_case`
- Variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Sheet names: `PascalCase` (e.g. `Users`, `Purchases`)
- Sheet columns: `snake_case` (e.g. `telegram_id`, `created_at`)
- Callback data: `snake_case` with underscores (e.g. `approve_purchase_ID`)

### Handler Registration
- All `@dp.message_handler` decorators must be registered **before** `executor.start_polling`
- Admin-only handlers must check `message.from_user.id in ADMIN_IDS` at handler entry
- State checks use the in-process `user_states` dict

### Google Sheets Access
- Always use `get_worksheet(name)` — never access worksheets directly
- Always use `get_all_rows(sheet)` — never use raw gspread cell methods for reads
- Always pass a dict to `append_row` and `update_row` — never pass a raw list
- Do not delete rows — only update `status` column to mark records as inactive

### Async Rules
- All handlers must be `async def`
- All Google Sheets calls must be wrapped with `asyncio.get_event_loop().run_in_executor` if synchronous
- Do not use `time.sleep` — use `await asyncio.sleep`
- Background tasks must be created with `asyncio.create_task`

## Business Rules (Do Not Change Without Explicit Authorization)

### Subscription
- Duration: exactly **180 days** — do not change
- Types: `normal` and `premium` only
- Test: exactly **5 minutes**, one per user lifetime

### Pricing
- Default Normal price: `$5 USD` (overridable via `NORMAL_PRICE` env var)
- Default Premium price: `$20 USD` (overridable via `PREMIUM_PRICE` env var)
- Reserve deposit: `$2 USD` — do not change without instruction

### Referral Commissions
- Level 1: **8%** of purchase amount
- Level 2: **12%** of purchase amount
- Commission capped by referrer's maximum approved purchase amount
- Auto-boost threshold: **10 direct referrals** → 10% L1 / 15% L2
- Deep affiliate (L3+): only for users in `Affiliates` sheet with `status=active`

### Withdrawals
- Minimum: **$10 USD**
- Methods: bank card (IRR) or USDT BEP20 only

### Purchases Sheet
- `admin_action` column is used for sheet-driven approvals — polled every 30 seconds
- Valid values: `approve`, `reject` — anything else is ignored
- After processing, `admin_action` is cleared

## Deployment Rules
- **Never commit** `.env`, `service-account.json`, or any secrets
- **Always** set environment variables on Render dashboard — not in files
- **Do not** change Render plan without cost review
- Polling mode only — webhook requires URL configuration not currently set up
- Single instance only — do not run multiple instances simultaneously (duplicate message processing)

## Admin Rules
- Admin IDs are set via `ADMIN_TELEGRAM_ID` and `ADMIN2_TELEGRAM_ID` env vars
- Admin status cannot be granted via bot commands — only via env vars
- Admins see an extended reply keyboard with admin-only buttons

## Data Rules
- Never hard-delete rows from Google Sheets — set `status` to `inactive` / `rejected`
- Timestamps always stored as ISO 8601 format: `YYYY-MM-DD HH:MM:SS`
- All monetary amounts stored as strings with 2 decimal places (e.g. `"5.00"`)
- `telegram_id` always stored as string, never integer

## Error Handling
- Critical startup failures (missing `BOT_TOKEN`, `SPREADSHEET_ID`) call `sys.exit(1)`
- Handler errors should be caught and a user-friendly Persian message sent
- Nobitex API failures fall back to 160,000 Toman — do not raise exceptions
