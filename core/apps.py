from django.apps import AppConfig


class CoreConfig(AppConfig):
    """App principal de pescAPP. No define modelos: no crea tablas."""

    name = "core"
    verbose_name = "pescAPP"
