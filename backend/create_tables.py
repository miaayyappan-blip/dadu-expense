import asyncio
from app.database.session import engine, Base
import app.models
async def go():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Tables created!')
asyncio.run(go())
