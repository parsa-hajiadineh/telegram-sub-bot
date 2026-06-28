# ROADMAP.md — Future Plans

## Status
No formal roadmap exists in the repository. The items below are derived from known limitations and missing features identified during code analysis.

---

## Identified Improvement Areas

### Critical (Bugs)
- [ ] Fix `massage.from_user.id` typo at line ~1080 in `check_reserve_block`
- [ ] Audit and fix Purchases sheet column index inconsistency (index 8 vs 9 for `status`)

### High Priority
- [ ] Add `.gitignore` to prevent committing secrets
- [ ] Add `.env.example` file for easier deployment setup
- [ ] Persist user state to a durable store (e.g. Redis or a Google Sheet) to survive restarts
- [ ] Add error logging (e.g. forward exceptions to admin Telegram ID or external service)

### Medium Priority
- [ ] Split `main.py` into separate modules for maintainability
  - `config.py` — environment variables
  - `sheets.py` — Google Sheets abstraction
  - `handlers/` — message and callback handlers
  - `jobs.py` — background tasks
  - `keyboards.py` — keyboard builders
- [ ] Implement webhook mode (remove `INSTANCE_MODE` dead code or implement it)
- [ ] Add duplicate purchase guard at checkout
- [ ] Add rate limiting on payment submission
- [ ] Add graceful shutdown (cancel asyncio tasks on SIGTERM)

### Low Priority
- [ ] Add unit tests for business logic (commissions, expiry, discount calculation)
- [ ] Add type hints to core functions
- [ ] Introduce a caching layer for frequently read sheets (e.g. `Config`, `DiscountCodes`)
- [ ] Monthly report scheduler: use a persistent cron instead of in-process timer
- [ ] Add admin notification for startup/restart events
- [ ] Upgrade to aiogram 3.x (breaking change — requires full rewrite of handlers)

---

## No Roadmap Items Found in Source
The source code contains no TODO/FIXME markers, no versioning tags, and no milestone references beyond the three-part concatenation structure (`# Part 1/3`, etc.).
