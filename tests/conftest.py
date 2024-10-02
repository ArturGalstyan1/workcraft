import os
import pathlib
import subprocess

import pytest
from workraft.utils import run_command


@pytest.fixture(scope="session", autouse=True)
def setup_docker_environment(request):
    current_dir = pathlib.Path(__file__).parent
    script_path = current_dir.parent / "scripts" / "renew_workraft_db.py"

    CONTAINER_NAME = "workraft-test"
    IMAGE_NAME = "workraft-test"
    WK_DB_HOST = "localhost"
    WK_DB_PORT = 5123
    WK_DB_USER = "workraft-test"
    WK_DB_PASS = "workraft-test"
    WK_DB_NAME = "workraft-test"

    # Prepare command
    command = ["python3 " + str(script_path)]

    command.extend(["--container-name", CONTAINER_NAME])
    command.extend(["--image-name", IMAGE_NAME])
    command.extend(["--db-port", str(WK_DB_PORT)])
    command.extend(["--db-user", WK_DB_USER])
    command.extend(["--db-pass", WK_DB_PASS])
    command.extend(["--db-name", WK_DB_NAME])
    command.extend(["--db-host", WK_DB_HOST])

    command = " ".join(command)

    try:
        run_command(command, debug=True)
        run_command("docker ps", debug=True)
        print("Docker environment setup completed successfully")
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Failed to setup Docker environment: {e}")
    yield
    # Add any cleanup code here if needed
    print("Tearing down Docker environment")
    try:
        subprocess.run([f"docker stop {CONTAINER_NAME}"], check=True, shell=True)
        subprocess.run([f"docker rm {CONTAINER_NAME}"], check=True, shell=True)
        print("Docker environment teardown completed successfully")
    except Exception as e:
        print(f"Failed to teardown Docker environment: {e}")
