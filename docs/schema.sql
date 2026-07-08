-- Telegram Subscription Bot — Supabase Schema
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id TEXT NOT NULL,
    username TEXT DEFAULT '',
    full_name TEXT DEFAULT '',
    email TEXT DEFAULT '',
    referral_code TEXT DEFAULT '',
    referred_by TEXT DEFAULT '',
    wallet_balance TEXT DEFAULT '0',
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT '',
    last_seen TEXT DEFAULT '',
    boost_data TEXT DEFAULT '',
    reserved_product TEXT DEFAULT '',
    reserved_amount TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS users_telegram_id_idx ON users(telegram_id);

CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGSERIAL PRIMARY KEY,
    telegram_id TEXT NOT NULL,
    username TEXT DEFAULT '',
    subscription_type TEXT DEFAULT '',
    status TEXT DEFAULT '',
    activated_at TEXT DEFAULT '',
    expires_at TEXT DEFAULT '',
    payment_method TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS subscriptions_telegram_id_idx ON subscriptions(telegram_id);

CREATE TABLE IF NOT EXISTS purchases (
    id BIGSERIAL PRIMARY KEY,
    purchase_id TEXT NOT NULL,
    telegram_id TEXT NOT NULL,
    username TEXT DEFAULT '',
    product TEXT DEFAULT '',
    amount_usd TEXT DEFAULT '',
    amount_irr TEXT DEFAULT '',
    payment_method TEXT DEFAULT '',
    transaction_id TEXT DEFAULT '',
    admin_action TEXT DEFAULT '',
    status TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    approved_at TEXT DEFAULT '',
    approved_by TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS purchases_purchase_id_idx ON purchases(purchase_id);
CREATE INDEX IF NOT EXISTS purchases_telegram_id_idx ON purchases(telegram_id);
CREATE INDEX IF NOT EXISTS purchases_admin_action_idx ON purchases(admin_action);

CREATE TABLE IF NOT EXISTS referrals (
    id BIGSERIAL PRIMARY KEY,
    referrer_id TEXT NOT NULL,
    referred_id TEXT NOT NULL,
    level TEXT DEFAULT '',
    commission_usd TEXT DEFAULT '',
    status TEXT DEFAULT '',
    purchase_id TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    paid_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS referrals_referrer_id_idx ON referrals(referrer_id);

CREATE TABLE IF NOT EXISTS withdrawals (
    id BIGSERIAL PRIMARY KEY,
    withdrawal_id TEXT NOT NULL,
    telegram_id TEXT NOT NULL,
    amount_usd TEXT DEFAULT '',
    method TEXT DEFAULT '',
    wallet_address TEXT DEFAULT '',
    card_number TEXT DEFAULT '',
    status TEXT DEFAULT '',
    requested_at TEXT DEFAULT '',
    processed_at TEXT DEFAULT '',
    processed_by TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS withdrawals_withdrawal_id_idx ON withdrawals(withdrawal_id);

CREATE TABLE IF NOT EXISTS tickets (
    id BIGSERIAL PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    telegram_id TEXT NOT NULL,
    username TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    message TEXT DEFAULT '',
    status TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    response TEXT DEFAULT '',
    responded_at TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS tickets_ticket_id_idx ON tickets(ticket_id);

CREATE TABLE IF NOT EXISTS config (
    id BIGSERIAL PRIMARY KEY,
    key TEXT NOT NULL,
    value TEXT DEFAULT '',
    description TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS config_key_idx ON config(key);

CREATE TABLE IF NOT EXISTS discount_codes (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    discount_percent TEXT DEFAULT '',
    max_uses TEXT DEFAULT '',
    used_count TEXT DEFAULT '0',
    valid_until TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    status TEXT DEFAULT 'active'
);
CREATE UNIQUE INDEX IF NOT EXISTS discount_codes_code_idx ON discount_codes(code);

CREATE TABLE IF NOT EXISTS gift_cards (
    id BIGSERIAL PRIMARY KEY,
    gift_code TEXT NOT NULL,
    product TEXT DEFAULT '',
    amount_usd TEXT DEFAULT '',
    buyer_id TEXT DEFAULT '',
    buyer_username TEXT DEFAULT '',
    recipient_id TEXT DEFAULT '',
    recipient_username TEXT DEFAULT '',
    message TEXT DEFAULT '',
    status TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    redeemed_at TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS gift_cards_gift_code_idx ON gift_cards(gift_code);

CREATE TABLE IF NOT EXISTS boost_codes (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    level1_percent TEXT DEFAULT '',
    level2_percent TEXT DEFAULT '',
    max_uses TEXT DEFAULT '',
    used_count TEXT DEFAULT '0',
    valid_until TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    status TEXT DEFAULT 'active'
);
CREATE UNIQUE INDEX IF NOT EXISTS boost_codes_code_idx ON boost_codes(code);

CREATE TABLE IF NOT EXISTS affiliates (
    id BIGSERIAL PRIMARY KEY,
    telegram_id TEXT NOT NULL,
    username TEXT DEFAULT '',
    full_name TEXT DEFAULT '',
    max_depth TEXT DEFAULT '',
    rate_percent TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS affiliates_telegram_id_idx ON affiliates(telegram_id);

CREATE TABLE IF NOT EXISTS user_states (
    id BIGSERIAL PRIMARY KEY,
    telegram_id TEXT NOT NULL,
    state_data JSONB NOT NULL DEFAULT '{}',
    updated_at TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS user_states_telegram_id_idx ON user_states(telegram_id);
