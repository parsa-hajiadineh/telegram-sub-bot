# CURRENT_STATUS.md — Project Status

## Status: Production / Active

## Code Quality

| Metric | Value |
|--------|-------|
| Total lines | ~6,630 |
| Files | 4 (main.py, requirements.txt, Dockerfile, render.yaml) |
| Test coverage | 0% — no tests exist |
| Documentation | None before this docs/ folder |
| Linting | Unknown — no linter config present |
| Type hints | None |

## Known Bugs

| # | Location | Description | Severity |
|---|----------|-------------|---------|
| 1 | `main.py` ~line 1080 | `massage.from_user.id` typo in `check_reserve_block` — crashes when reserve block check runs | High |
| 2 | `main.py` Purchases handler | Column index inconsistency: some code uses index 8, some index 9 for `status`/`approved_at` in Purchases sheet — can cause wrong-column writes | Medium |

## Known Limitations / Missing Features

| # | Description |
|---|-------------|
| 1 | `INSTANCE_MODE` env var is defined but never used — webhook mode not implemented |
| 2 | In-memory state (`dict`) is lost on restart — users in mid-flow lose progress |
| 3 | No `.gitignore` — risk of committing `service-account.json` if added locally |
| 4 | No `.env.example` file in repo |
| 5 | No error logging to external service (Sentry, etc.) |
| 6 | No rate limiting on user actions |
| 7 | No duplicate purchase prevention at DB level (sheet has no unique constraints) |
| 8 | Google Sheets full-scan on every read — performance degrades as data grows |
| 9 | No graceful shutdown handling — active asyncio tasks dropped on SIGTERM |
| 10 | `send_monthly_reports` only triggers if bot is running at exactly 1st of month 10:00 UTC |

## Deployment Status
- **Platform:** Render (free tier)
- **Runtime:** Docker (Python 3.11-slim)
- **Health check:** aiohttp on `$PORT`
- **Scaling:** Single instance only (polling mode does not support multi-instance)

## Dependencies Status
| Package | Pinned Version | Status |
|---------|---------------|--------|
| aiogram | 2.25.1 | Pinned — aiogram 3.x is a breaking change |
| aiohttp | >=3.8.0,<3.9.0 | Range-pinned |
| gspread | 6.0.0 | Pinned |
| google-auth | 2.25.2 | Pinned |

## What Works (as of last analysis)
- User registration with email confirmation
- Referral system (L1/L2 commissions + auto-boost)
- Normal and Premium subscription purchase via USDT and bank card
- Pre-payment reserve flow
- Gift card creation and redemption
- Discount codes
- Wallet balance and withdrawals (card + USDT)
- Support ticket system
- Admin inline approval (purchases, withdrawals)
- Sheet-driven approval (poll every 30s)
- Channel access management (invite links, auto-removal)
- 5-minute free test channel
- Background expiry reminders (7d, 3d, 1d)
- Monthly user reports
- Deep affiliate commission system
- Boost codes (manual and auto at 10 referrals)
- Admin broadcast
- Admin dashboard stats
- Nobitex live USDT/IRR rate with fallback
- Health check endpoint for Render

## What Needs Attention (Priority Order)
1. Fix `massage` typo bug (line ~1080)
2. Verify Purchases sheet column index consistency
3. Add `.gitignore`
4. Add `.env.example`
5. Persist user state to survive restarts
6. Add error logging
