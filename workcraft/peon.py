import asyncio
import json
import traceback

from beartype.typing import Any
from loguru import logger
from pydantic import ValidationError
from sqlalchemy import Connection, text

from workcraft.core import Workcraft, WorkerStateSingleton
from workcraft.db import (
    check_connection,
    DBEngineSingleton,
    update_worker_state_sync,
    verify_database_setup,
)
from workcraft.models import DBConfig, Task, TaskStatus
from workcraft.settings import settings
from workcraft.utils import sleep


def dequeue_task(db_config: DBConfig, workcraft: Workcraft) -> Task | None:
    worker_state = WorkerStateSingleton.get()

    def mark_task_as_invalid(conn: Connection, task_id: str):
        logger.error(f"Marking task {task_id} as INVALID")
        statement = text("""
            UPDATE bountyboard
            SET status = 'INVALID'
            WHERE id = :id
        """)
        conn.execute(statement, {"id": task_id})
        conn.commit()

    registered_tasks = workcraft.tasks.keys()
    with DBEngineSingleton.get(db_config).connect() as conn:
        try:
            statement = text("""
                SELECT bountyboard.id
                FROM bountyboard
                JOIN peon ON peon.id = :worker_id
                WHERE (bountyboard.status = 'PENDING'
                    OR (bountyboard.status = 'FAILURE'
                        AND bountyboard.retry_on_failure = TRUE
                        AND bountyboard.retry_count <= bountyboard.retry_limit))
                AND bountyboard.task_name IN :registered_tasks
                AND JSON_CONTAINS(peon.queues, JSON_QUOTE(bountyboard.queue))
                ORDER BY bountyboard.created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """)
            id_result = conn.execute(
                statement,
                {
                    "registered_tasks": tuple(registered_tasks),
                    "worker_id": worker_state.id,
                },
            ).fetchone()

            if id_result:
                # Then fetch the complete row using the ID
                statement = text("""
                    SELECT * FROM bountyboard
                    WHERE id = :id
                    FOR UPDATE
                """)
                result = conn.execute(statement, {"id": id_result[0]}).fetchone()

                if result:
                    resultdict = result._asdict()
                    try:
                        task = Task.from_db_data(resultdict)
                        statement = text("""
                            UPDATE bountyboard
                            SET status = 'RUNNING',
                                worker_id = :worker_id
                            WHERE id = :id
                        """)
                        conn.execute(
                            statement,
                            {"id": task.id, "worker_id": WorkerStateSingleton.get().id},
                        )
                        conn.commit()
                        WorkerStateSingleton.update(
                            status="WORKING", current_task=task.id
                        )
                        update_worker_state_sync(
                            db_config, worker_state=WorkerStateSingleton.get()
                        )
                        return task
                    except ValidationError as e:
                        logger.error(
                            f"Error validating task: {e}. Invalid task: {resultdict}"
                        )
                        mark_task_as_invalid(conn, resultdict["id"])
                        return None
                    except Exception as e:
                        logger.error(f"Error dequeuing task: {e}")
                        mark_task_as_invalid(conn, resultdict["id"])
                        return None
        except Exception as e:
            logger.error(f"Error querying task: {e}")
            return None
        return None


async def run_peon(db_config: DBConfig, workcraft: Workcraft):
    verify_database_setup(db_config)
    WorkerStateSingleton.update(status="IDLE", current_task=None)
    update_worker_state_sync(db_config, worker_state=WorkerStateSingleton.get())

    logger.info("Tasks:")
    for name, _ in workcraft.tasks.items():
        logger.info(f"- {name}")

    logger.success("Zug zug. Ready to work!")
    connection_fine = False
    while True:
        try:
            while not check_connection(db_config):
                logger.error("Database connection lost. Retrying...")
                connection_fine = False
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error checking database connection: {e}")
            continue

        if not connection_fine:
            logger.success("Database connection established.")
            connection_fine = True

        try:
            await sleep(settings)
            task = dequeue_task(db_config, workcraft)
            if task:
                logger.info(f"Dequeued task: {task.task_name}, ID: {task.id}")
                logger.debug(f"Task payload: {task.payload}")
                await execute_task(db_config, task, workcraft)
        except asyncio.CancelledError:
            logger.info("Main loop cancelled. Shutting down...")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            logger.error(traceback.format_exc())
            await asyncio.sleep(1)


async def execute_task(
    db_config: DBConfig,
    task: Task,
    workcraft: Workcraft,
) -> None:
    try:
        await execute_prerun_handler(workcraft, task)
    except Exception as e:
        logger.error(f"Prerun handler failed: {e}, continuing...")

    result = None
    status = TaskStatus.RUNNING

    try:
        result = await execute_main_task(workcraft, task)
        logger.debug(f"Task {task.task_name} returned: {result}")
        status = TaskStatus.SUCCESS
    except Exception as e:
        logger.error(f"Task {task.task_name} failed: {e}")
        logger.error(traceback.format_exc())
        status = TaskStatus.FAILURE
        result = traceback.format_exc() + "\n" + str(e)
    finally:
        logger.info(f"Task {task.task_name} finished with status: {status}")
        with DBEngineSingleton.get(db_config).connect() as conn:
            result = json.dumps(result)
            update_task_status(conn, task.id, status, result)
        task.status = status
        task.result = result
        task.retry_count = (
            task.retry_count + 1 if status == TaskStatus.FAILURE else task.retry_count
        )
        WorkerStateSingleton.update(status="IDLE", current_task=None)
        update_worker_state_sync(db_config, WorkerStateSingleton.get())
        try:
            await execute_postrun_handler(workcraft, task)
        except Exception as e:
            logger.error(f"Postrun handler failed: {e}")
            logger.error(traceback.format_exc())


async def execute_prerun_handler(workcraft: Workcraft, task: Task) -> None:
    if workcraft.prerun_handler_fn is not None:
        await execute_handler(
            workcraft.prerun_handler_fn,
            [task.id, task.task_name] + task.payload.prerun_handler_args,
            task.payload.prerun_handler_kwargs,
        )


async def execute_main_task(workcraft: Workcraft, task: Task) -> Any:
    task_handler = workcraft.tasks[task.task_name]
    if asyncio.iscoroutinefunction(task_handler):
        return await task_handler(
            task.id, *task.payload.task_args, **task.payload.task_kwargs
        )
    else:
        return task_handler(
            task.id, *task.payload.task_args, **task.payload.task_kwargs
        )


async def execute_postrun_handler(
    workcraft: Workcraft,
    task: Task,
) -> None:
    if workcraft.postrun_handler_fn is not None:
        await execute_handler(
            workcraft.postrun_handler_fn,
            [task.id, task.task_name, task.result, task.status.value]
            + task.payload.postrun_handler_args,
            task.payload.postrun_handler_kwargs,
        )


async def execute_handler(handler: Any, args: list, kwargs: dict) -> None:
    if asyncio.iscoroutinefunction(handler):
        await handler(*args, **kwargs)
    else:
        handler(*args, **kwargs)


def update_task_status(
    conn: Connection, task_id: str, status: TaskStatus, result: Any | None
) -> None:
    try:
        conn.execute(
            text(
                """
UPDATE bountyboard
SET status = :status,
    result = :res,
    retry_count = CASE WHEN :status = 'FAILURE' THEN retry_count + 1 ELSE retry_count END
WHERE id = :id
                """  # noqa
            ),
            {
                "status": status.value,
                "res": result,
                "id": task_id,
            },
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to update task {task_id} status to {status}: {e}")
        raise e
