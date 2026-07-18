#!/usr/bin/env bash
set -e

python manage.py migrate --noinput
exec python main.py
