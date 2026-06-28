# DECISIONS.md — Architecture Decision Records

## ADR-001: Single-File Architecture
**Status:** Existing  
**Date:** Unknown  
**Decision:** All application code lives in `main.py` (~6,630 lines)  
**Reason:** Unknown — the file shows evidence of being three separate parts concatenated into one (`# Part 1/3`, `# Part 2/3`, `# Part 3A/3B` comments)  
**Consequence:** High coupling, difficult to navigate, merge conflicts likely at scale

---

## ADR-002: Google Sheets as Database
**Status:** Existing  
**Date:** Unknown  
**Decision:** Use Google Sheets instead of a relational or NoSQL database  
**Reason:** Unknown — likely chosen for zero infrastructure cost, visual admin access, and no database setup  
**Consequence:**
- No indexes → O(n) reads on every operation
- No transactions → possible data inconsistency under concurrent writes
- No referential integrity
- Google Sheets API rate limit (300 req/min) becomes a ceiling
- Free and human-readable by non-technical admins

---

## ADR-003: aiogram 2.x (Not 3.x)
**Status:** Existing  
**Date:** Unknown  
**Decision:** Pin aiogram to version 2.25.1  
**Reason:** Unknown — aiogram 3.x is a breaking API change; migration would require rewriting all handlers  
**Consequence:** Stuck on older API; aiogram 3.x has better middleware, FSM, and router support

---

## ADR-004: Polling Mode Only
**Status:** Existing  
**Date:** Unknown  
**Decision:** Use Telegram long-polling; webhook mode not implemented despite `INSTANCE_MODE` env var  
**Reason:** Unknown — likely simpler setup on Render without needing a public HTTPS URL configured  
**Consequence:** Cannot scale horizontally; single instance required; `INSTANCE_MODE` env var is dead code

---

## ADR-005: In-Memory User State
**Status:** Existing  
**Date:** Unknown  
**Decision:** Store conversation state in a Python `dict` in process memory  
**Reason:** Unknown — simplest implementation, no external dependency  
**Consequence:** All in-progress user flows are lost on bot restart; users must start over

---

## ADR-006: Render Free Tier Deployment
**Status:** Existing  
**Date:** Unknown  
**Decision:** Deploy on Render free tier using Docker  
**Reason:** Unknown — zero cost  
**Consequence:** Service may sleep on inactivity; health endpoint at `/` and `/health` keeps it alive; limited resources; no SLA

---

## ADR-007: Nobitex for USDT/IRR Rate
**Status:** Existing  
**Date:** Unknown  
**Decision:** Use Nobitex `USDTIRT` orderbook API for live exchange rate with 160,000 Toman fallback  
**Reason:** Unknown — likely most accessible Iranian exchange API  
**Consequence:** Rate is live but can drift from actual payment rates; admin can override via `Config` sheet

---

## ADR-008: Sheet-Driven Admin Approvals
**Status:** Existing  
**Date:** Unknown  
**Decision:** Admins can approve/reject purchases by writing `approve`/`reject` in the `admin_action` column of the Purchases sheet; bot polls every 30 seconds  
**Reason:** Provides a non-bot interface for approvals (spreadsheet access)  
**Consequence:** Up to 30-second delay between sheet edit and bot action; requires admins to have spreadsheet access
