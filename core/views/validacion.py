"""B · Validación · Integración MongoDB -> PostgreSQL (R3)."""
from django.contrib import messages
from django.shortcuts import render
from django.views.decorators.http import require_POST
from pymongo.errors import PyMongoError

from core import consultas
from core.repositorios import recepciones_repo
from core.servicios import validacion
from core.views.comun import error_mongo, mapa_proveedores, volver


def panel(request):
    consultas.establecer_accion("READ · Recepciones por validar (MongoDB)")
    contexto = {
        "pendientes": recepciones_repo.listar_por_estado("pendiente"),
        "validadas": recepciones_repo.listar_por_estado("validada", limite=10),
        "proveedores": mapa_proveedores(),
    }
    return render(request, "core/validacion/panel.html", contexto)


def _mostrar(request, resultado: validacion.ResultadoValidacion) -> None:
    {"success": messages.success, "warning": messages.warning}.get(resultado.nivel, messages.error)(
        request, resultado.mensaje
    )


# =====================================================================
# R3 · Validar: transacción PostgreSQL + marca en MongoDB
# =====================================================================
@require_POST
def validar(request, uuid):
    consultas.establecer_accion("R3 · Validar recepción → compra oficial (transacción)")
    _mostrar(request, validacion.validar_recepcion(uuid, request.id_usuario))
    return volver(request, "/validacion/")


# =====================================================================
# R3 · Forzar revalidación (demo): la rechaza el UNIQUE de PostgreSQL
# =====================================================================
@require_POST
def forzar(request, uuid):
    consultas.establecer_accion("R3 · Forzar revalidación (demo): ¿quién protege? PostgreSQL")
    _mostrar(request, validacion.forzar_revalidacion(uuid, request.id_usuario))
    return volver(request, "/validacion/")


@require_POST
def desfasar(request, uuid):
    """Demo: deja MongoDB en 'pendiente' aunque la compra ya exista."""
    consultas.establecer_accion("Demo · Simular desfase de MongoDB")
    try:
        r = recepciones_repo.desfasar_demo(uuid)
        if r.modified_count:
            messages.info(
                request,
                "MongoDB quedó desfasado: la recepción figura 'pendiente' pero su compra existe en "
                "PostgreSQL. Al validarla, el UNIQUE lo detecta y se reconcilia.",
            )
        else:
            messages.warning(request, "Solo se puede desfasar una recepción validada.")
    except PyMongoError as exc:
        error_mongo(request, exc)
    return volver(request, "/validacion/")
