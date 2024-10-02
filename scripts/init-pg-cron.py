import os
import subprocess
import time

import fire
from dotenv import load_dotenv


def psql_command(db, command, host, port, user, password):
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    result = subprocess.run(
        ["psql", "-h", host, "-p", str(port), "-U", user, "-d", db, "-c", command],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def wait_for_postgres(db, host, port, user, password):
    while True:
        try:
            psql_command(db, "SELECT 1", host, port, user, password)
            break
        except subprocess.CalledProcessError:
            print("Waiting for PostgreSQL to be ready...")
            time.sleep(1)


def init_postgres(
    db_host: str = "localhost",
    db_port: str = "5432",
    db_user: str = "workraft-user",
    db_pass: str = "workraft-pass",
    db_name: str = "workraft-db",
    use_env: bool = False,
    env_file: str = ".env",
):
    if use_env:
        load_dotenv(env_file)
        db_host = os.getenv("DB_HOST", db_host)
        db_port = os.getenv("DB_PORT", db_port)
        db_user = os.getenv("DB_USER", db_user)
        db_pass = os.getenv("DB_PASS", db_pass)
        db_name = os.getenv("DB_NAME", db_name)

    print("Initializing PostgreSQL")
    print(f"Host: {db_host}")
    print(f"Port: {db_port}")
    print(f"User: {db_user}")
    print(f"Database: {db_name}")

    # Wait for PostgreSQL to be ready
    wait_for_postgres(db_name, db_host, db_port, db_user, db_pass)

    # Check if pg_cron is already in shared_preload_libraries
    current_libs = psql_command(
        db_name, "SHOW shared_preload_libraries;", db_host, db_port, db_user, db_pass
    )
    print(f"{current_libs=}")
    if "pg_cron" not in current_libs:
        print(
            "pg_cron is not in shared_preload_libraries. "
            "It needs to be added manually to postgresql.conf and the server restarted."
        )
        print("After doing so, run this script again.")
        return

    # Set cron.database_name
    psql_command(
        db_name,
        f"ALTER SYSTEM SET cron.database_name = '{db_name}';",
        db_host,
        db_port,
        db_user,
        db_pass,
    )

    # Add logging configurations
    psql_command(
        db_name,
        "ALTER SYSTEM SET log_statement TO 'none';",
        db_host,
        db_port,
        db_user,
        db_pass,
    )
    psql_command(
        db_name,
        "ALTER SYSTEM SET log_min_messages TO 'notice';",
        db_host,
        db_port,
        db_user,
        db_pass,
    )
    psql_command(
        db_name,
        "ALTER SYSTEM SET log_min_error_statement TO 'error';",
        db_host,
        db_port,
        db_user,
        db_pass,
    )

    # Enable pg_cron extension
    psql_command(
        db_name,
        "CREATE EXTENSION IF NOT EXISTS pg_cron;",
        db_host,
        db_port,
        db_user,
        db_pass,
    )

    # Reload PostgreSQL configuration
    psql_command(
        db_name, "SELECT pg_reload_conf();", db_host, db_port, db_user, db_pass
    )

    print(f"pg_cron initialization completed for database: {db_name}")


if __name__ == "__main__":
    fire.Fire(init_postgres)
