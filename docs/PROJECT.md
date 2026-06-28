# PROJECT.md — Telegram Subscription Bot

## Project Name
telegram-sub-bot

## Purpose
A Telegram bot for selling and managing channel subscriptions. Users can purchase Normal or Premium access to private Telegram channels, pay via USDT (BEP20) or Iranian bank card (IRR), and earn referral commissions. Admins manage the entire lifecycle through the bot's inline interface and Google Sheets.

## Language & Runtime
- **Language:** Python 3.11
- **Framework:** aiogram 2.25.1 (polling mode)

## Execution Model
Single polling process. The bot connects to Telegram via long-polling and simultaneously runs an aiohttp HTTP server for health checks.

## Repository Structure
```
telegram-sub-bot/
├── main.py            # Entire application (~6,630 lines)
├── requirements.txt   # Python dependencies
├── Dockerfile         # Python 3.11-slim container
├── render.yaml        # Render deployment config
└── docs/              # Project documentation
```

## Dependencies
| Package | Version | Role |
|---------|---------|------|
| aiogram | 2.25.1 | Telegram Bot SDK |
| aiohttp | >=3.8.0,<3.9.0 | Health HTTP server + Nobitex API |
| gspread | 6.0.0 | Google Sheets read/write |
| google-auth | 2.25.2 | Google service account auth |

## Deployment Platform
- **Host:** Render (free tier)
- **Runtime:** Docker
- **Health endpoint:** `GET /` or `GET /health` → `"OK"` on `$PORT` (default 8000)

## Environment Variables (Required)
| Variable | Purpose |
|----------|---------|
| `BOT_TOKEN` | Telegram bot token |
| `SPREADSHEET_ID` | Google Spreadsheet ID (acts as database) |
| `GOOGLE_CREDENTIALS` | Service account JSON (string or base64) |

## Environment Variables (Optional)
| Variable | Default | Purpose |
|----------|---------|---------|
| `ADMIN_TELEGRAM_ID` | — | Primary admin user ID |
| `ADMIN2_TELEGRAM_ID` | — | Secondary admin user ID |
| `REQUIRED_CHANNELS` | `""` | Comma-separated channel IDs for mandatory join check |
| `NORMAL_CHANNEL_ID` | — | Normal subscription channel ID |
| `PREMIUM_CHANNEL_ID` | — | Premium subscription channel ID |
| `TEST_CHANNEL_ID` | — | 5-minute trial channel ID |
| `NORMAL_PRICE` | `5` | Normal plan price (USD) |
| `PREMIUM_PRICE` | `20` | Premium plan price (USD) |
| `TETHER_WALLET` | `""` | USDT BEP20 wallet address |
| `CARD_NUMBER` | `""` | Bank card number for IRR payments |
| `CARD_HOLDER` | `""` | Card holder name |
| `PORT` | `8000` | Health check HTTP port |
| `BOT_USERNAME` | `YourBot` | Used in referral/share links |
| `SUPPORT_USERNAME` | `@YourSupportAccount` | Shown in card payment flow |
| `INSTANCE_MODE` | `polling` | Defined but unused; webhook not implemented |

## Subscription Plans
| Plan | Price | Duration |
|------|-------|---------|
| Normal | $5 USD | 180 days (6 months) |
| Premium | $20 USD | 180 days (6 months) |
| Test | Free | 5 minutes |

## Payment Methods
1. **USDT BEP20** — user sends to wallet, uploads screenshot, admin approves
2. **Iranian Bank Card (IRR)** — amount calculated via Nobitex USDTIRT rate, user uploads receipt, admin approves
3. **Wallet balance** — accumulated referral commissions
4. **Gift card** — redeemable codes
5. **Pre-payment reserve** — $2 deposit locks a slot; completion required later

## Key Business Rules
- Referral Level 1: 8% commission
- Referral Level 2: 12% commission
- Commission capped by referrer's maximum approved purchase amount
- Level 3+ commissions only for designated "deep affiliates"
- Auto-boost at 10 direct referrals: 10% L1 / 15% L2
- Minimum withdrawal amount: $10 USD
- Withdrawal methods: Bank card or USDT BEP20
