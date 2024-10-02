import pytest
from workraft.__main__ import CLI
from workraft.models import DBConfig


@pytest.mark.asyncio
async def test_setup_tables():
    # read os env vars:
    WK_DB_HOST = "localhost"
    WK_DB_PORT = 5123
    WK_DB_USER = "workraft-test"
    WK_DB_PASS = "workraft-test"
    WK_DB_NAME = "workraft-test"

    db_config: DBConfig = DBConfig(
        host=WK_DB_HOST,
        port=WK_DB_PORT,
        user=WK_DB_USER,
        password=WK_DB_PASS,
        database=WK_DB_NAME,
    )

    await CLI.build_stronghold(db_config=db_config)
