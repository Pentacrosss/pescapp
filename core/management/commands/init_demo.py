"""
python manage.py init_demo · arranque automático (Docker).

Espera a PostgreSQL y MongoDB. Si el esquema o la colección no existen,
los crea y carga la semilla; si ya existen, conserva los datos.
"""
from django.core.management.base import BaseCommand

from core.servicios import esquema, semilla


class Command(BaseCommand):
    help = "Espera a las bases y crea esquema + datos semilla si faltan."

    def add_arguments(self, parser):
        parser.add_argument("--forzar", action="store_true", help="Reinicia aunque ya existan datos.")

    def handle(self, *args, **opciones):
        esquema.esperar_bases(salida=self.stdout.write)
        existe = esquema.existe_esquema_postgres() and esquema.existe_coleccion_mongo()
        if existe and not opciones["forzar"]:
            self.stdout.write("Esquema existente: se conservan los datos (use reset_demo para reiniciar).")
            return
        self.stdout.write("Creando esquema PostgreSQL, colección MongoDB y datos semilla...")
        resumen = semilla.reiniciar_demo()
        self.stdout.write(
            self.style.SUCCESS(
                "Listo: {recepciones} recepciones, {compras} compras, {ventas} ventas, "
                "{cierres} cierres.".format(**resumen)
            )
        )
