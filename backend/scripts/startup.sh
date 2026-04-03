#!/bin/sh
# Startup script: handles both fresh DB and existing DB scenarios.
# Fresh DB: create_all → stamp alembic head (skip ALTER migrations)
# Existing DB: alembic upgrade head (apply pending migrations)
set -e

PYTHONPATH=/app

# Check if alembic_version table exists (i.e., DB has been initialized before)
HAS_ALEMBIC=$(python -c "
import asyncio
from sqlalchemy import text
from app.core.database import engine
async def check():
    async with engine.connect() as conn:
        r = await conn.execute(text(\"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version')\"))
        row = r.scalar()
        if row:
            r2 = await conn.execute(text('SELECT COUNT(*) FROM alembic_version'))
            count = r2.scalar()
            print('yes' if count > 0 else 'no')
        else:
            print('no')
asyncio.run(check())
" 2>/dev/null || echo "no")

if [ "$HAS_ALEMBIC" = "yes" ]; then
    echo "Existing DB detected, running alembic upgrade head..."
    PYTHONPATH=/app alembic upgrade head
else
    echo "Fresh DB detected, creating tables via create_all + stamping alembic head..."
    python -c "
import asyncio
from app.core.database import engine, Base
import app.models  # noqa: ensure all models registered
async def create():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
asyncio.run(create())
"
    PYTHONPATH=/app alembic stamp head
    echo "Tables created and alembic stamped at head."
fi

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers --forwarded-allow-ips '*' --access-log
