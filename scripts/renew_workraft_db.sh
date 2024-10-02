#!/bin/bash

# Default values
CONTAINER_NAME="workraft-db"
IMAGE_NAME="workraft-postgres"
DB_PORT="5432"
DB_HOST="localhost"
DB_USER="postgres"
DB_PASS="mysecretpassword"
DB_NAME="workraft"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --container-name)
        CONTAINER_NAME="$2"
        shift # past argument
        shift # past value
        ;;
        --image-name)
        IMAGE_NAME="$2"
        shift # past argument
        shift # past value
        ;;
        --db-port)
        DB_PORT="$2"
        shift # past argument
        shift # past value
        ;;
        --db-host)
        DB_HOST="$2"
        shift # past argument
        shift # past value
        ;;
        --db-user)
        DB_USER="$2"
        shift # past argument
        shift # past value
        ;;
        --db-pass)
        DB_PASS="$2"
        shift # past argument
        shift # past value
        ;;
        --db-name)
        DB_NAME="$2"
        shift # past argument
        shift # past value
        ;;
        *)    # unknown option
        echo "Unknown option: $1"
        exit 1
        ;;
    esac
done

# Check if .env file exists and source it
if [ -f .env ]; then
    source .env
fi

# Set variables, prioritizing command-line args, then env vars, then defaults
WK_DB_HOST="${DB_HOST:-${WK_DB_HOST:-localhost}}"
WK_DB_PORT="${DB_PORT:-${WK_DB_PORT:-5432}}"
WK_DB_USER="${DB_USER:-${WK_DB_USER:-postgres}}"
WK_DB_PASS="${DB_PASS:-${WK_DB_PASS:-mysecretpassword}}"
WK_DB_NAME="${DB_NAME:-${WK_DB_NAME:-workraft}}"

# Build the Docker image
docker build -t $IMAGE_NAME .

# Check if container is running and stop it
if docker ps -a | grep -q $CONTAINER_NAME; then
    echo "Stopping and removing existing $CONTAINER_NAME container..."
    docker stop $CONTAINER_NAME
    docker rm $CONTAINER_NAME
fi

# Run the Docker container with environment variables
docker run -d \
    --name $CONTAINER_NAME \
    -p "${WK_DB_PORT}:5432" \
    -e POSTGRES_USER="${WK_DB_USER}" \
    -e POSTGRES_PASSWORD="${WK_DB_PASS}" \
    -e POSTGRES_DB="${WK_DB_NAME}" \
    -e WK_DB_HOST="${WK_DB_HOST}" \
    $IMAGE_NAME

echo "Container Name: $CONTAINER_NAME"
echo "Image Name: $IMAGE_NAME"
echo "Database Host: $WK_DB_HOST"
echo "Database Port: $WK_DB_PORT"
echo "Database User: $WK_DB_USER"
echo "Database Password: $WK_DB_PASS"
echo "Database Name: $WK_DB_NAME"
