from datetime import datetime
from typing import Any, Dict, Optional

from config import logger, supabase_client

TABLE = "user_states"
MIGRATION_HINT = "Run docs/migrations/001_create_user_states.sql in Supabase SQL Editor."


class UserStates:
    """In-memory user flow state backed by Supabase."""

    def __init__(self):
        self._cache: Dict[int, Dict[str, Any]] = {}
        self._persist_enabled: Optional[bool] = None

    def load_all(self) -> None:
        if not self._ensure_table():
            return

        try:
            result = supabase_client.table(TABLE).select("telegram_id, state_data").execute()
            self._cache.clear()
            for row in result.data or []:
                telegram_id = int(row["telegram_id"])
                state_data = row.get("state_data") or {}
                if state_data:
                    self._cache[telegram_id] = state_data
            logger.info(f"✅ Loaded {len(self._cache)} user state(s) from Supabase")
        except Exception as e:
            logger.exception(f"Failed to load user states: {e}")

    def _ensure_table(self) -> bool:
        if self._persist_enabled is not None:
            return self._persist_enabled

        try:
            supabase_client.table(TABLE).select("telegram_id").limit(1).execute()
            self._persist_enabled = True
            logger.info("✅ Table: user_states")
        except Exception as e:
            self._persist_enabled = False
            logger.error(f"❌ Table user_states: {e}. {MIGRATION_HINT}")

        return self._persist_enabled

    def __contains__(self, key: int) -> bool:
        return key in self._cache

    def __getitem__(self, key: int) -> Dict[str, Any]:
        return self._cache[key]

    def __setitem__(self, key: int, value: Dict[str, Any]) -> None:
        self._cache[key] = value
        self._upsert(key, value)

    def get(self, key: int, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._cache.get(key, default if default is not None else {})

    def pop(self, key: int, default: Any = None) -> Any:
        if key not in self._cache:
            return default
        value = self._cache.pop(key)
        self._delete(key)
        return value

    def _upsert(self, telegram_id: int, data: Dict[str, Any]) -> None:
        if not self._ensure_table():
            return

        try:
            supabase_client.table(TABLE).upsert(
                {
                    "telegram_id": str(telegram_id),
                    "state_data": data,
                    "updated_at": datetime.utcnow().replace(microsecond=0).isoformat(),
                },
                on_conflict="telegram_id",
            ).execute()
        except Exception as e:
            logger.error(f"Failed to persist user state for {telegram_id}: {e}")

    def _delete(self, telegram_id: int) -> None:
        if not self._ensure_table():
            return

        try:
            supabase_client.table(TABLE).delete().eq(
                "telegram_id", str(telegram_id)
            ).execute()
        except Exception as e:
            logger.error(f"Failed to delete user state for {telegram_id}: {e}")


user_states = UserStates()
