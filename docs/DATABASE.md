# DATABASE.md — Data Layer

## Database Engine
**Supabase (PostgreSQL)**

All data is stored in a Supabase project. Connection via `supabase-py` client using `SUPABASE_URL` and `SUPABASE_KEY` environment variables.

Schema file: `docs/schema.sql` — run once in Supabase SQL Editor to create all tables.

## Compatibility Layer
The application uses a thin wrapper layer (`get_all_rows`, `append_row`, `update_row`, `find_user`) that maintains the same interface as the previous Google Sheets layer. Each data row returned by `get_all_rows` has the Supabase internal `id` appended at index `len(columns)` — used internally by `update_row` to identify the record. All other column indexes remain unchanged.

## Tables

---

### `Users`
| Column | Type | Description |
|--------|------|-------------|
| `telegram_id` | string | Telegram user ID (primary key) |
| `username` | string | Telegram username (may be empty) |
| `full_name` | string | Display name |
| `email` | string | Required at registration |
| `referral_code` | string | Unique 6-character code |
| `referred_by` | string | `telegram_id` of referrer |
| `wallet_balance` | decimal string | Commission balance in USD |
| `status` | string | e.g. `active` |
| `created_at` | ISO datetime | Registration timestamp |
| `last_seen` | ISO datetime | Last interaction |
| `boost_data` | string | Format: `boost:CODE:L1:L2` or auto-boost marker |
| `reserved_product` | string | `normal` / `premium` — set during reserve flow |
| `reserved_amount` | decimal string | Amount paid toward reserve |

---

### `Subscriptions`
| Column | Type | Description |
|--------|------|-------------|
| `telegram_id` | string | User ID |
| `username` | string | Telegram username |
| `subscription_type` | string | `normal` / `premium` |
| `status` | string | `active` / `expired` |
| `activated_at` | ISO datetime | Activation timestamp |
| `expires_at` | ISO datetime | Expiry timestamp (180 days from activation) |
| `payment_method` | string | `usdt` / `card` / `wallet` / `gift` |

---

### `Purchases`
| Column | Type | Description |
|--------|------|-------------|
| `purchase_id` | string | Unique purchase ID |
| `telegram_id` | string | Buyer user ID |
| `username` | string | Telegram username |
| `product` | string | See product values below |
| `amount_usd` | decimal string | USD amount |
| `amount_irr` | decimal string | IRR equivalent at time of purchase |
| `payment_method` | string | `usdt` / `card` / `wallet` / `gift` |
| `transaction_id` | string | User-submitted TX hash or receipt ref |
| `admin_action` | string | Sheet-driven approval: `approve` / `reject` |
| `status` | string | `pending` / `approved` / `rejected` |
| `created_at` | ISO datetime | Submission timestamp |
| `approved_at` | ISO datetime | Approval timestamp |
| `approved_by` | string | Admin telegram_id or `sheet` |
| `notes` | string | Free-form notes |

**Product values:**
`normal`, `premium`, `test`, `gift_normal`, `gift_premium`, `reserve_normal`, `reserve_premium`, `complete_normal`, `complete_premium`

---

### `Referrals`
| Column | Type | Description |
|--------|------|-------------|
| `referrer_id` | string | User who referred |
| `referred_id` | string | User who was referred |
| `level` | integer string | `1` or `2` (or `3+` for affiliates) |
| `commission_usd` | decimal string | Commission amount |
| `status` | string | `pending` / `paid` |
| `purchase_id` | string | Linked purchase |
| `created_at` | ISO datetime | Commission creation timestamp |
| `paid_at` | ISO datetime | When credited to wallet |

---

### `Withdrawals`
| Column | Type | Description |
|--------|------|-------------|
| `withdrawal_id` | string | Unique ID |
| `telegram_id` | string | Requester ID |
| `amount_usd` | decimal string | Requested amount |
| `method` | string | `usdt` / `card` |
| `wallet_address` | string | USDT BEP20 address (if method=usdt) |
| `card_number` | string | Bank card (if method=card) |
| `status` | string | `pending` / `processed` / `rejected` |
| `requested_at` | ISO datetime | Request timestamp |
| `processed_at` | ISO datetime | Processing timestamp |
| `processed_by` | string | Admin telegram_id |
| `notes` | string | Admin notes |

---

### `Tickets`
| Column | Type | Description |
|--------|------|-------------|
| `ticket_id` | string | Unique ID |
| `telegram_id` | string | User ID |
| `username` | string | Telegram username |
| `subject` | string | Ticket subject |
| `message` | string | Ticket body |
| `status` | string | `open` / `answered` / `closed` |
| `created_at` | ISO datetime | Creation timestamp |
| `response` | string | Admin reply text |
| `responded_at` | ISO datetime | Reply timestamp |

---

### `Config`
| Column | Type | Description |
|--------|------|-------------|
| `key` | string | Config key (e.g. `usdt_price_irr`) |
| `value` | string | Config value |
| `description` | string | Human-readable description |

**Known keys:**
- `usdt_price_irr` — manual override for USDT/IRR rate

---

### `DiscountCodes`
| Column | Type | Description |
|--------|------|-------------|
| `code` | string | Unique discount code |
| `discount_percent` | integer string | Discount percentage |
| `max_uses` | integer string | Maximum allowed redemptions |
| `used_count` | integer string | Current redemption count |
| `valid_until` | ISO date | Expiry date |
| `created_by` | string | Admin telegram_id |
| `created_at` | ISO datetime | Creation timestamp |
| `status` | string | `active` / `inactive` |

---

### `GiftCards`
| Column | Type | Description |
|--------|------|-------------|
| `gift_code` | string | Unique gift code |
| `product` | string | `normal` / `premium` |
| `amount_usd` | decimal string | Monetary value |
| `buyer_id` | string | Buyer telegram_id |
| `buyer_username` | string | Buyer username |
| `recipient_id` | string | Recipient telegram_id (if sent) |
| `recipient_username` | string | Recipient username |
| `message` | string | Personal message |
| `status` | string | `active` / `redeemed` |
| `created_at` | ISO datetime | Creation timestamp |
| `redeemed_at` | ISO datetime | Redemption timestamp |

---

### `BoostCodes`
| Column | Type | Description |
|--------|------|-------------|
| `code` | string | Unique boost code |
| `level1_percent` | integer string | L1 referral commission override % |
| `level2_percent` | integer string | L2 referral commission override % |
| `max_uses` | integer string | Max redemptions |
| `used_count` | integer string | Current redemption count |
| `valid_until` | ISO date | Expiry date |
| `created_by` | string | Admin telegram_id |
| `created_at` | ISO datetime | Creation timestamp |
| `status` | string | `active` / `inactive` |

---

### `Affiliates`
| Column | Type | Description |
|--------|------|-------------|
| `telegram_id` | string | Affiliate user ID |
| `username` | string | Telegram username |
| `full_name` | string | Display name |
| `max_depth` | integer string | Max referral depth (3+) |
| `rate_percent` | decimal string | Commission rate for deep levels |
| `status` | string | `active` / `inactive` |
| `created_at` | ISO datetime | Registration timestamp |
| `created_by` | string | Admin telegram_id |
| `notes` | string | Admin notes |

---

## Access Patterns
- Reads: `get_all_rows()` → full table fetch ordered by `id`; `find_user()` → filtered query by `telegram_id`
- Writes: `append_row()` → INSERT; `update_row()` → UPDATE WHERE id = ?
- Indexes on high-frequency lookup columns (see `schema.sql`)
- No foreign key enforcement (maintains backward compatibility with original design)

## Limitations
- All column values stored as TEXT (for backward compatibility with string-based code)
- No transactions — concurrent writes can still cause race conditions
- `get_all_rows()` fetches all rows for full-scan operations (same pattern as before)

## Environment Variables
| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL` | Supabase project URL (e.g. `https://xxxx.supabase.co`) |
| `SUPABASE_KEY` | Supabase anon/public API key |
