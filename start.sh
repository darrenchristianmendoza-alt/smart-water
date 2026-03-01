#!/bin/bash
python -c "from database.db import init_db, seed_historical_data; init_db(); seed_historical_data()"
python collector/generator.py &
gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 1 --threads 2
