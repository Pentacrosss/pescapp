"""
Middlewares de pescAPP.

- ConsultasMiddleware: abre el registro de consultas de cada petición
  (panel "Consulta ejecutada"). Si la acción termina en redirección,
  guarda sus consultas y las muestra en la página siguiente.
- UsuarioActualMiddleware: "Usuario actual" elegido en la barra
  superior, guardado en cookie (sin login real).
"""
from __future__ import annotations

import logging

from core import consultas
from core.repositorios import catalogo_repo

COOKIE_ACCION = "pescapp_accion"
COOKIE_USUARIO = "pescapp_usuario"

log = logging.getLogger(__name__)


class ConsultasMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        id_previo = request.COOKIES.get(COOKIE_ACCION)
        request.accion_previa = consultas.recuperar_accion(id_previo)
        token = consultas.iniciar(ruta=request.path, metodo=request.method)
        try:
            response = self.get_response(request)
            estado = consultas.estado_actual()
        finally:
            consultas.finalizar(token)

        if id_previo:
            response.delete_cookie(COOKIE_ACCION)
        if estado.consultas and response.status_code in (301, 302, 303):
            nuevo_id = consultas.guardar_accion(estado)
            response.set_cookie(COOKIE_ACCION, nuevo_id, max_age=300, samesite="Lax")
        return response


class UsuarioActualMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.usuarios = []
        request.usuario_actual = None
        request.id_usuario = None
        try:
            with consultas.silenciado():  # infraestructura: no ensucia el panel
                request.usuarios = catalogo_repo.listar_usuarios()
        except Exception as exc:  # noqa: BLE001 - la página mostrará el error real
            log.warning("No se pudo leer la tabla usuario: %s", exc)

        elegido = request.COOKIES.get(COOKIE_USUARIO)
        for usuario in request.usuarios:
            if str(usuario["id_usuario"]) == elegido:
                request.usuario_actual = usuario
        if request.usuario_actual is None and request.usuarios:
            request.usuario_actual = request.usuarios[0]
        if request.usuario_actual:
            request.id_usuario = request.usuario_actual["id_usuario"]
        return self.get_response(request)
