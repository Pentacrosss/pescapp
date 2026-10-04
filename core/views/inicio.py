"""G · Inicio, usuario actual, reinicio de la demo y Bitácora."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core import consultas
from core.middleware import COOKIE_USUARIO
from core.repositorios import catalogo_repo, cierre_repo, recepciones_repo
from core.servicios import semilla
from core.views.comun import volver


def inicio(request):
    consultas.establecer_accion("READ · Inicio: conteos de ambos motores")
    contexto = {
        "conteo_pg": catalogo_repo.conteo_tablas(),
        "conteo_mongo": recepciones_repo.conteo_por_estado(),
        "pendientes_hoy": len(recepciones_repo.pendientes_del_dia()),
        "ultima_cerrada": cierre_repo.ultima_fecha_cerrada(),
    }
    return render(request, "core/inicio.html", contexto)


@require_POST
def cambiar_usuario(request):
    respuesta = volver(request)
    respuesta.set_cookie(COOKIE_USUARIO, request.POST.get("id_usuario", ""), max_age=60 * 60 * 24 * 30, samesite="Lax")
    return respuesta


@require_POST
def reiniciar_demo(request):
    resumen = semilla.reiniciar_demo()
    consultas.establecer_accion("Reiniciar datos de demo")
    messages.success(
        request,
        "Datos de demo restaurados en PostgreSQL y MongoDB: {recepciones} recepciones, "
        "{compras} compras, {ventas} ventas y {cierres} cierres.".format(**resumen),
    )
    return redirect("/?reiniciado=1")


def bitacora(request):
    return render(request, "core/bitacora.html", {"operaciones": consultas.bitacora()})
