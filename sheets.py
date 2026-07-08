from typing import Any, List, Optional, Tuple

from config import logger, supabase_client, SHEET_DEFINITIONS, TABLE_MAP


# ============================================
# DATABASE HELPERS (Supabase)
# ============================================

async def get_all_rows(sheet_name: str) -> List[List[str]]:
    """Get all rows — returns [header_row, row1, row2, ...]
    Each data row has the Supabase internal id appended at the end (index len(headers)).
    """
    try:
        table = TABLE_MAP.get(sheet_name)
        if not table:
            logger.error(f"Unknown sheet: {sheet_name}")
            return []
        headers = SHEET_DEFINITIONS.get(sheet_name, [])
        result = supabase_client.table(table).select("*").order("id").execute()
        rows = [headers]
        for record in result.data:
            row = [str(record.get(h, "") or "") for h in headers]
            row.append(record["id"])  # supabase id at index len(headers)
            rows.append(row)
        return rows
    except Exception as e:
        logger.exception(f"Failed to get rows from {sheet_name}: {e}")
        return []


async def append_row(sheet_name: str, row: List[Any]) -> bool:
    """Insert a new row into the table"""
    try:
        table = TABLE_MAP.get(sheet_name)
        headers = SHEET_DEFINITIONS.get(sheet_name, [])
        if not table or not headers:
            return False
        data = {col: str(row[i]) if i < len(row) and row[i] is not None else ""
                for i, col in enumerate(headers)}
        supabase_client.table(table).insert(data).execute()
        return True
    except Exception as e:
        logger.exception(f"Failed to append row to {sheet_name}: {e}")
        return False


async def update_row(sheet_name: str, row_index: int, row: List[Any]) -> bool:
    """Update an existing row using Supabase id stored at row[len(headers)]"""
    try:
        table = TABLE_MAP.get(sheet_name)
        headers = SHEET_DEFINITIONS.get(sheet_name, [])
        if not table or not headers:
            return False
        supabase_id = row[len(headers)] if len(row) > len(headers) else None
        if supabase_id is None:
            logger.error(f"No supabase id found in row for {sheet_name}")
            return False
        data = {col: str(row[i]) if i < len(row) and row[i] is not None else ""
                for i, col in enumerate(headers)}
        supabase_client.table(table).update(data).eq("id", supabase_id).execute()
        return True
    except Exception as e:
        logger.exception(f"Failed to update row in {sheet_name}: {e}")
        return False


async def find_user(telegram_id: int) -> Optional[Tuple[int, List[str]]]:
    """Find user by telegram_id — returns (supabase_id, row) or None"""
    try:
        result = supabase_client.table("users").select("*").eq(
            "telegram_id", str(telegram_id)
        ).execute()
        if result.data:
            headers = SHEET_DEFINITIONS["Users"]
            record = result.data[0]
            row = [str(record.get(h, "") or "") for h in headers]
            row.append(record["id"])
            return record["id"], row
        return None
    except Exception as e:
        logger.exception(f"Failed to find user {telegram_id}: {e}")
        return None
