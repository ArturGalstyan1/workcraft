import os
import time

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import create_engine, Engine, text

from workcraft.models import DBConfig, WorkerState
from workcraft.settings import settings


class DBEngineSingleton:
    _engine: Engine | None = None

    @staticmethod
    def get(db_config: DBConfig) -> Engine:
        if DBEngineSingleton._engine is None:
            _engine = create_engine(DBConfig.get_uri(db_config))
            DBEngineSingleton._engine = _engine
        assert (
            DBEngineSingleton._engine is not None
        ), "DBEngineSingleton._engine is None"
        return DBEngineSingleton._engine


def get_db_config() -> DBConfig:
    load_dotenv()

    host = os.getenv("WK_DB_HOST", None)
    port = os.getenv("WK_DB_PORT", None)
    user = os.getenv("WK_DB_USER", None)
    pswd = os.getenv("WK_DB_PASS", None)
    name = os.getenv("WK_DB_NAME", None)
    use_ssl = os.getenv("WK_DB_USE_SSL", None)
    ssl_path = os.getenv("WK_DB_SSL_PATH", None)

    assert host, "WK_DB_HOST is not set"
    assert port, "WK_DB_PORT is not set"
    assert user, "WK_DB_USER is not set"
    assert pswd, "WK_DB_PASS is not set"
    assert name, "WK_DB_NAME is not set"

    if use_ssl is None:
        use_ssl = False
    else:
        use_ssl = use_ssl.lower() == "true"

    if use_ssl:
        assert ssl_path, "WK_DB_SSL_PATH is not set"
    return DBConfig(
        host=host,
        port=int(port),
        user=user,
        password=pswd,
        database=name,
        use_ssl=use_ssl,
        ssl_path=ssl_path,
    )


def update_worker_state_sync(db_config: DBConfig, worker_state: WorkerState):
    with DBEngineSingleton.get(db_config).connect() as conn:
        statement = text("""
            INSERT INTO peon (id, status, last_heartbeat, current_task, queues)
            VALUES (:id, :status, NOW(), :current_task, :queues)
            ON DUPLICATE KEY UPDATE
            status = :status,
            last_heartbeat = NOW(),
            current_task = :current_task,
            queues = :queues
        """)

        conn.execute(
            statement,
            {
                "id": worker_state.id,
                "status": worker_state.status,
                "current_task": worker_state.current_task,
                "queues": ",".join(worker_state.queues),
            },
        )
        conn.commit()


def send_heartbeat_sync(db_config: DBConfig, worker_id: str) -> None:
    conn = None
    while True:
        try:
            with DBEngineSingleton.get(db_config).connect() as conn:
                update_query = [
                    "UPDATE peon",
                    "SET last_heartbeat = NOW()",
                    f'WHERE id = "{worker_id}"',
                ]
                conn.execute(text(" ".join(update_query)))
                conn.commit()
                time.sleep(settings.DB_PEON_HEARTBEAT_INTERVAL)
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")
        finally:
            if conn:
                conn.close()


def verify_database_setup(db_config: DBConfig) -> bool:
    with DBEngineSingleton.get(db_config).connect() as conn:
        # Check tables exist
        tables_query = text("""
            SELECT COUNT(*) = 3 as tables_exist FROM information_schema.tables
            WHERE table_name IN ('logs', 'peon', 'bountyboard')
            AND table_schema = :db_name
        """)
        tables_exist = conn.execute(
            tables_query, {"db_name": db_config.database}
        ).scalar()

        if not tables_exist:
            return False

        # Verify key columns and types
        structure_query = text("""
SELECT
    (SELECT column_type FROM information_schema.columns
        WHERE table_name = 'peon' AND column_name = 'status') = "enum('IDLE','PREPARING','WORKING','OFFLINE')"
    AND
    (SELECT column_type FROM information_schema.columns
        WHERE table_name = 'bountyboard' AND column_name = 'status') = "enum('PENDING','RUNNING','SUCCESS','FAILURE','INVALID')"
    as correct_structure
        """)  # noqa
        return bool(conn.execute(structure_query).scalar())
