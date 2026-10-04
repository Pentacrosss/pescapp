"""Punto de entrada WSGI de pescAPP."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pescapp.settings")

application = get_wsgi_application()
