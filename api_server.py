#!/usr/bin/env python
"""
Django REST API Server Runner
Run this to start the Django REST API server separately from the Discord bot
"""

import os
import sys
import django
from django.core.management import execute_from_command_line

if __name__ == '__main__':
    # Set Django settings module
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    
    # Setup Django
    django.setup()
    
    # Run Django development server
    host = os.getenv('API_HOST', '0.0.0.0')
    port = os.getenv('API_PORT', '8000')
    
    print(f"Starting Django REST API server on {host}:{port}")
    print("API endpoints available at:")
    print(f"  - http://{host}:{port}/api/")
    print(f"  - http://{host}:{port}/spotify/callback/")
    print("Press Ctrl+C to stop the server")
    
    # Start the server
    execute_from_command_line(['manage.py', 'runserver', f'{host}:{port}'])
