"""python manage.py reset_demo · restaura ambas bases al estado inicial."""
from django.core.management.base import BaseCommand

from core.servicios import esquema, semilla


class Command(BaseCommand):
    help = "Recrea el esquema PostgreSQL y la colección MongoDB y carga los datos semilla."

    def handle(self, *args, **opciones):
        esquema.esperar_bases(salida=self.stdout.write)
        self.stdout.write("Reiniciando datos de demo (PostgreSQL + MongoDB)...")
        resumen = semilla.reiniciar_demo()
        self.stdout.write(
            self.style.SUCCESS(
                "Listo: {recepciones} recepciones, {compras} compras, {ventas} ventas, "
                "{cierres} cierres.".format(**resumen)
            )
        )
