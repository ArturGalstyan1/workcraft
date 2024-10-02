import os
import pathlib

import fire
from dotenv import load_dotenv
from workraft.utils import run_command


def renew(
    db_host: str | None = "localhost",
    db_port: str | None = "5432",
    db_user: str | None = "workraft-user",
    db_pass: str | None = "workraft-pass",
    db_name: str | None = "workraft-db",
    use_env: bool = False,
    env_file: str = ".env",
    container_name: str = "workraft",
    image_name: str = "workraft",
):
    print("Renewing database")
    print(f"Host: {db_host}")
    print(f"Port: {db_port}")
    print(f"User: {db_user}")
    print(f"Pass: {db_pass}")
    print(f"Name: {db_name}")

    if use_env:
        load_dotenv(env_file)
        db_host = os.getenv("DB_HOST", None)
        db_port = os.getenv("DB_PORT", None)
        db_user = os.getenv("DB_USER", None)
        db_pass = os.getenv("DB_PASS", None)
        db_name = os.getenv("DB_NAME", None)

    assert db_host is not None, "DB_HOST is required"
    assert db_port is not None, "DB_PORT is required"
    assert db_user is not None, "DB_USER is required"
    assert db_pass is not None, "DB_PASS is required"
    assert db_name is not None, "DB_NAME is required"

    # stop and remove container if it exists
    docker_stop_cmd = f"docker stop {container_name}"
    docker_rm_cmd = f"docker rm {container_name}"

    try:
        run_command(docker_stop_cmd, debug=True)
        run_command(docker_rm_cmd, debug=True)
    except Exception as e:
        print(
            f"Failed to stop and remove container {e}, likely because it does not exist"
        )

    dockerfile_path = pathlib.Path(__file__).parent.parent

    docker_build_cmd = (
        f"docker build -t {image_name}",
        f"-f {dockerfile_path}/Dockerfile {dockerfile_path}",
    )

    print("Building Docker image")
    try:
        run_command(" ".join(docker_build_cmd), debug=True)
        print("Docker image built successfully")
    except Exception as e:
        print(f"Failed to build Docker image: {e}")
        return

    docker_run_cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "-p",
        f"{db_port}:5432",
        "-e",
        f"POSTGRES_USER={db_user}",
        "-e",
        f"POSTGRES_PASSWORD={db_pass}",
        "-e",
        f"POSTGRES_DB={db_name}",
        image_name,
    ]

    print("Running Docker container")
    try:
        run_command(" ".join(docker_run_cmd), debug=True)
        print("Docker container running successfully")
    except Exception as e:
        print(f"Failed to run Docker container: {e}")
        return


if __name__ == "__main__":
    fire.Fire(renew)
