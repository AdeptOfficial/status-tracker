#!/bin/bash
# Run tests in Docker container
#
# Usage:
#   ./run_tests.sh              # Run all tests
#   ./run_tests.sh -v           # Verbose output
#   ./run_tests.sh tests/test_infrastructure.py  # Run specific test file

set -e

cd "$(dirname "$0")"

# Build test image with test dependencies
docker build -t status-tracker-test -f - . <<'EOF'
FROM python:3.12-slim
WORKDIR /app

# Install test dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pytest pytest-asyncio

# Copy application code
COPY app/ ./app/
COPY tests/ ./tests/
COPY pytest.ini .

# Copy webhook fixtures (symlink doesn't work in Docker COPY)
COPY docs/flows/captured-webhooks/ ./tests/fixtures/webhooks/

ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite:///:memory:

CMD ["pytest"]
EOF

# Run tests
docker run --rm status-tracker-test pytest "$@"
