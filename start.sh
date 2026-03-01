#!/bin/bash
set -e

echo "=== Initializing Database ==="
python -c "import sys; sys.path.insert(0, '.'); from database.db import init_db, seed_historical_data; init_db(); seed_historical_data()"

echo "=== Starting Data Generator ==="
python collector/generator.py &

echo "=== Starting Flask ==="
exec gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 1 --threads 2
