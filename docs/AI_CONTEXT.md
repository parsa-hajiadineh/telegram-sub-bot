# AI_CONTEXT.md — Management Summary for AI Assistants

> Read this file first in every new chat session. It provides a complete context of the project.

---

## What This Project Is
A **Telegram subscription bot** written in Python. It sells access to private Telegram channels (Normal $5/6mo, Premium $20/6mo). Users pay via USDT or Iranian bank card. The bot manages the full lifecycle: registration, payment, channel access, referrals, wallet, and support.

---

## Tech Stack (Single Sentence)
Python 3.11 · aiogram 2.25.1 · Google Sheets (database) · aiohttp (health server) · Deployed on Render via Docker

---

## File Structure
```
main.py          ← ENTIRE application (~6,630 lines, 3 concatenated parts)
requirements.txt ← 4 dependencies
Dockerfile       ← python:3.11-slim
render.yaml      ← Render web service (free tier, Docker)
docs/            ← This documentation folder
```

---

## Database
Google Sheets (no SQL). Spreadsheet ID from `SPREADSHEET_ID` env var.

**Sheets:** `Users`, `Subscriptions`, `Purchases`, `Referrals`, `Withdrawals`, `Tickets`, `Config`, `DiscountCodes`, `GiftCards`, `BoostCodes`, `Affiliates`

All reads are full-sheet scans. No indexes, no transactions.

---

## Required Environment Variables
| Variable | Purpose |
|----------|---------|
| `BOT_TOKEN` | Telegram bot token |
| `SPREADSHEET_ID` | Google Spreadsheet ID |
| `GOOGLE_CREDENTIALS` | Service account JSON (string or base64) |

**Important channel IDs:** `NORMAL_CHANNEL_ID`, `PREMIUM_CHANNEL_ID`, `TEST_CHANNEL_ID`  
**Admin IDs:** `ADMIN_TELEGRAM_ID`, `ADMIN2_TELEGRAM_ID`  
**Prices:** `NORMAL_PRICE` (default 5), `PREMIUM_PRICE` (default 20)  
**Payments:** `TETHER_WALLET`, `CARD_NUMBER`, `CARD_HOLDER`

---

## Key Business Rules
- Subscription: 180 days
- Referral L1: 8%, L2: 12% — capped by referrer's max purchase
- Auto-boost at 10 direct referrals: 10%/15%
- Deep affiliates (L3+): Affiliates sheet only
- Reserve deposit: $2 to lock slot
- Min withdrawal: $10 via card or USDT BEP20
- Test channel: 5 minutes, one per user

---

## Admin Interface
- Extended reply keyboard (admin users only)
- Inline approval buttons for purchases and withdrawals
- Sheet-driven approvals: write `approve`/`reject` in Purchases.admin_action → bot processes in 30s
- Admin commands: `/stats`, `/dashboard`, `/broadcast`, `/msg`, `/reply`, `/createcode`, `/createboost`, `/makeaffiliate`, etc.

---

## Background Jobs
| Job | Interval | Purpose |
|-----|----------|---------|
| `poll_sheets_auto_process` | 30s | Process sheet-driven admin actions |
| `schedule_expiry` | Per subscription | Remove from channel at expiry |
| `schedule_expiry_reminders` | 7d/3d/1d | Renewal reminder DMs |
| `send_monthly_reports` | Monthly (1st, 10:00 UTC) | Activity summary to users |
| `schedule_test_removal` | 5 min | Remove test channel users |

---

## Known Bugs
1. **Line ~1080:** `massage.from_user.id` typo → crashes `check_reserve_block` (High)
2. **Purchases sheet:** Column index 8 vs 9 inconsistency for `status` (Medium)

---

## Known Limitations
- No tests, no linter, no type hints
- In-memory state lost on restart
- No `.gitignore` or `.env.example`
- `INSTANCE_MODE` env var defined but unused (webhook not implemented)
- Single instance only (polling mode)
- Google Sheets full-scan on every read

---

## Navigating main.py
| Section | Lines (approx) |
|---------|---------------|
| Config & env vars | 1–100 |
| Google Sheets layer | 100–400 |
| User/business logic | 400–824 |
| Keyboard builders | 824–1100 |
| Message & callback handlers | 1100–4000 |
| Admin system | 4000–5500 |
| Background jobs | 5500–6200 |
| Startup / entry point | 6200–6630 |

---

## Detailed Documentation
| File | Contents |
|------|----------|
| `docs/PROJECT.md` | Full project overview, env vars, plans, pricing |
| `docs/ARCHITECTURE.md` | Component diagram, layer breakdown, known structural issues |
| `docs/DATABASE.md` | All 11 sheets with column-by-column schema |
| `docs/API.md` | All commands, callback patterns, external APIs |
| `docs/CURRENT_STATUS.md` | Bugs, limitations, what works |
| `docs/PROJECT_RULES.md` | Code conventions, business rules, deployment rules |
| `docs/ROADMAP.md` | Identified improvements and priorities |
| `docs/DECISIONS.md` | Architecture decisions (ADR-001 through ADR-008) |
