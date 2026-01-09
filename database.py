
import os
import asyncpg
import logging
from typing import List, Optional
import asyncio

logger = logging.getLogger("gemini.db")

class DatabaseManager:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.database_url = os.getenv("DATABASE_URL")

    async def connect(self):
        if not self.database_url:
            logger.warning("DATABASE_URL not set. Database features disabled.")
            return

        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10
            )
            await self._init_schema()
            logger.info("✅ Database connected successfully")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise e

    async def _init_schema(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS gemini_accounts (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255),
                    secure_c_ses TEXT NOT NULL,
                    host_c_oses TEXT,
                    csesidx TEXT NOT NULL,
                    config_id TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    request_count BIGINT DEFAULT 0,
                    last_used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- Migration: Add column if not exists
                ALTER TABLE gemini_accounts ADD COLUMN IF NOT EXISTS request_count BIGINT DEFAULT 0;
                
                -- Create index for faster lookups if needed
                CREATE INDEX IF NOT EXISTS idx_accounts_active ON gemini_accounts(is_active);
            """)

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def fetch_active_accounts(self) -> List[dict]:
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM gemini_accounts 
                WHERE is_active = TRUE 
                ORDER BY last_used_at ASC NULLS FIRST
            """)
            return [dict(row) for row in rows]

    async def increment_account_usage(self, account_id: int):
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE gemini_accounts 
                SET last_used_at = NOW(), request_count = request_count + 1
                WHERE id = $1
            """, account_id)

    async def update_account_usage(self, account_id: int):
        # Legacy method, redirect to increment if needed, or just update timestamp
        # For now, let's just update timestamp to not break compatibility if called elsewhere without intent to increment count
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE gemini_accounts 
                SET last_used_at = NOW() 
                WHERE id = $1
            """, account_id)

    async def add_account(self, name: str, secure_c_ses: str, host_c_oses: str, csesidx: str, config_id: str):
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO gemini_accounts (name, secure_c_ses, host_c_oses, csesidx, config_id)
                VALUES ($1, $2, $3, $4, $5)
            """, name, secure_c_ses, host_c_oses, csesidx, config_id)

    async def get_all_accounts(self) -> List[dict]:
        if not self.pool: return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM gemini_accounts ORDER BY id ASC")
            return [dict(row) for row in rows]

    async def update_account(self, id: int, data: dict):
        if not self.pool: return
        set_clauses = []
        values = []
        idx = 1
        for key in ["name", "secure_c_ses", "host_c_oses", "csesidx", "config_id", "is_active"]:
            if key in data:
                set_clauses.append(f"{key} = ${idx}")
                values.append(data[key])
                idx += 1
        
        if not set_clauses: return
        
        values.append(id)
        query = f"UPDATE gemini_accounts SET {', '.join(set_clauses)} WHERE id = ${idx}"
        
        async with self.pool.acquire() as conn:
            await conn.execute(query, *values)

    async def delete_account(self, id: int):
        if not self.pool: return
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM gemini_accounts WHERE id = $1", id)

db = DatabaseManager()
