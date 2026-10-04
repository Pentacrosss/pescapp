"""Utilidades compartidas por las vistas."""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from core.bd import mongo, pg
from core.repositorios import catalogo_repo


def volver(request, por_defecto: str = "/"):
    """Redirige al parámetro next si es una ruta local segura."""
    destino = request.POST.get("next") or request.GET.get("next")
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return redirect(destino)
    return redirect(por_defecto)


def error_pg(request, exc: BaseException, prefijo: str = "Rechazado por PostgreSQL") -> None:
    """Alerta con el mensaje real del motor (el detalle completo queda en el panel)."""
    messages.error(request, f"{prefijo}: {pg.mensaje_motor(exc)}")


def error_mongo(request, exc: BaseException, prefijo: str = "Rechazado por MongoDB") -> None:
    messages.error(request, f"{prefijo}: {mongo.mensaje_motor(exc)}")


def mapa_proveedores() -> dict[int, str]:
    return {p["id_proveedor"]: p["nombre"] for p in catalogo_repo.listar_proveedores()}


def mapa_usuarios(request) -> dict[int, str]:
    return {u["id_usuario"]: u["nombre"] for u in getattr(request, "usuarios", [])}
