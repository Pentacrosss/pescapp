"""
A · Muelle · MongoDB · CRUD de recepciones (R1, R2).

  CREATE  captura (UUID en el navegador) + api_sincronizar (upsert idempotente)
  READ    lista con filtros, pendientes del día, detalle, plan de consulta
  UPDATE  corregir línea, agregar atributo, rechazar (solo pendientes)
  DELETE  eliminar (solo pendiente o rechazada)
"""
from __future__ import annotations

import json

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from pymongo.errors import PyMongoError

from core import consultas
from core.bd import mongo
from core.plantillas_atributos import PLANTILLAS_ATRIBUTOS, convertir_valor
from core.repositorios import catalogo_repo, recepciones_repo
from core.servicios import esquema
from core.utilidades import a_entero, a_fecha, hoy
from core.views.comun import error_mongo, mapa_proveedores, mapa_usuarios


# =====================================================================
# CREATE · Captura en muelle (pantalla)
# =====================================================================
def captura(request):
    consultas.establecer_accion("READ · Captura en muelle: catálogo local del dispositivo")
    productos = [
        {"id_producto": p["id_producto"], "especie": p["especie"], "presentacion": p["presentacion"]}
        for p in catalogo_repo.listar_productos()
    ]
    proveedores = catalogo_repo.listar_proveedores()
    datos = {
        "productos": productos,
        "plantillas": PLANTILLAS_ATRIBUTOS,
        "url_api": reverse("muelle_api_sincronizar"),
        "url_detalle": reverse("muelle_detalle", args=["UUID"]),
    }
    contexto = {
        "datos_captura": datos,
        "proveedores": proveedores,
        "total_documentos": recepciones_repo.conteo_por_estado()["total"],
    }
    return render(request, "core/muelle/captura.html", contexto)


# =====================================================================
# CREATE · R1 · API de sincronización (upsert idempotente por _id)
# Recibe { "recepciones": [doc, ...] } desde el navegador.
# =====================================================================
@require_POST
def api_sincronizar(request):
    try:
        datos = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)
    consultas.establecer_accion(datos.get("titulo") or "R1 · Sincronizar recepciones")

    resultados = []
    for crudo in datos.get("recepciones", []):
        documento = recepciones_repo.normalizar_documento(crudo)
        resultado = recepciones_repo.sincronizar_recepcion(documento)
        resultados.append(resultado)

    return JsonResponse(
        {
            "resultados": resultados,
            "consultas": [c.como_dict() for c in consultas.consultas_actuales()],
        },
        json_dumps_params={"ensure_ascii": False, "default": str},
    )


# =====================================================================
# READ · Lista con filtros (estado, fecha, proveedor, especie)
# =====================================================================
def lista(request):
    consultas.establecer_accion("READ · Recepciones con filtros (MongoDB)")
    estado = request.GET.get("estado") or None
    fecha = a_fecha(request.GET.get("fecha"))
    id_proveedor = a_entero(request.GET.get("proveedor"))
    especie = request.GET.get("especie") or None

    filtro = recepciones_repo.construir_filtro(estado, fecha, id_proveedor, especie)
    recepciones = recepciones_repo.listar(filtro)
    plan = None
    if request.GET.get("plan"):
        consultas.establecer_accion("READ · Plan de consulta (explain) de la lista")
        plan = recepciones_repo.explicar(filtro, recepciones_repo.ORDEN_LISTA)

    contexto = {
        "titulo": "Recepciones del muelle",
        "recepciones": recepciones,
        "plan": plan,
        "filtros": {
            "estado": estado or "",
            "fecha": fecha.isoformat() if fecha else "",
            "proveedor": id_proveedor or "",
            "especie": especie or "",
        },
        "estados": recepciones_repo.ESTADOS,
        "especies": [e["nombre_comun"] for e in catalogo_repo.listar_especies()],
        "proveedores": mapa_proveedores(),
        "usuarios_mapa": mapa_usuarios(request),
        "con_filtros": True,
        "comando": mongo.a_mongosh(filtro, compacto=True),
    }
    return render(request, "core/muelle/lista.html", contexto)


# =====================================================================
# READ · R1 · Pendientes del día (usa el índice estado + capturado_en)
# =====================================================================
def pendientes(request):
    consultas.establecer_accion("READ · Pendientes del día (índice estado + capturado_en)")
    filtro = recepciones_repo.filtro_pendientes_del_dia()
    recepciones = recepciones_repo.pendientes_del_dia()
    plan = None
    if request.GET.get("plan"):
        consultas.establecer_accion("READ · Plan de consulta (explain) de pendientes del día")
        plan = recepciones_repo.explicar(filtro, recepciones_repo.ORDEN_PENDIENTES)
    contexto = {
        "titulo": f"Pendientes del día {hoy():%d/%m/%Y}",
        "recepciones": recepciones,
        "plan": plan,
        "proveedores": mapa_proveedores(),
        "usuarios_mapa": mapa_usuarios(request),
        "con_filtros": False,
        "comando": mongo.a_mongosh(filtro, compacto=True),
    }
    return render(request, "core/muelle/lista.html", contexto)


# =====================================================================
# READ · Detalle (atributos distintos por línea)
# =====================================================================
def detalle(request, uuid):
    consultas.establecer_accion("READ · Detalle de recepción (MongoDB)")
    documento = recepciones_repo.obtener(uuid)
    if documento is None:
        raise Http404("La recepción no existe")
    productos = {p["id_producto"]: p for p in catalogo_repo.listar_productos()}
    contexto = {
        "doc": documento,
        "productos": productos,
        "proveedores": mapa_proveedores(),
        "usuarios_mapa": mapa_usuarios(request),
    }
    return render(request, "core/muelle/detalle.html", contexto)


# =====================================================================
# UPDATE · Corregir peso o precio de una línea ($set, solo pendiente)
# =====================================================================
@require_POST
def corregir_linea(request, uuid):
    consultas.establecer_accion("UPDATE · Corregir línea (MongoDB $set)")
    indice = a_entero(request.POST.get("indice"), 0)
    peso = recepciones_repo.a_numero(request.POST["peso_kg"]) if request.POST.get("peso_kg") else None
    precio = recepciones_repo.a_numero(request.POST["precio_kg"]) if request.POST.get("precio_kg") else None
    if peso is None and precio is None:
        messages.warning(request, "Indique el nuevo peso o el nuevo precio.")
        return redirect("muelle_detalle", uuid=uuid)
    try:
        r = recepciones_repo.corregir_linea(uuid, indice, peso, precio)
    except PyMongoError as exc:
        error_mongo(request, exc)
        return redirect("muelle_detalle", uuid=uuid)
    if r.matched_count == 0:
        messages.warning(request, "No se modificó: solo se corrigen recepciones pendientes (matched_count = 0).")
    else:
        messages.success(
            request,
            f"Línea {indice + 1} corregida con $set (matched_count = {r.matched_count}, "
            f"modified_count = {r.modified_count}).",
        )
    return redirect("muelle_detalle", uuid=uuid)


# =====================================================================
# UPDATE · R2 · Agregar atributo nuevo a una línea (sin cambiar esquema)
# =====================================================================
@require_POST
def agregar_atributo(request, uuid):
    consultas.establecer_accion("UPDATE · R2 · Agregar atributo (MongoDB $set)")
    indice = a_entero(request.POST.get("indice"), 0)
    clave = (request.POST.get("clave") or "").strip().replace(" ", "_")
    if not clave or "." in clave or clave.startswith("$"):
        messages.error(request, "Clave inválida: no puede estar vacía, contener '.' ni empezar con '$'.")
        return redirect("muelle_detalle", uuid=uuid)
    valor = convertir_valor(request.POST.get("valor", ""))
    try:
        r = recepciones_repo.agregar_atributo(uuid, indice, clave, valor)
    except PyMongoError as exc:
        error_mongo(request, exc)
        return redirect("muelle_detalle", uuid=uuid)
    if r.matched_count == 0:
        messages.warning(request, "No se modificó: solo se editan recepciones pendientes (matched_count = 0).")
    else:
        messages.success(
            request,
            f"Atributo «{clave}» agregado a la línea {indice + 1} sin cambiar el esquema "
            f"(modified_count = {r.modified_count}).",
        )
    return redirect("muelle_detalle", uuid=uuid)


# =====================================================================
# UPDATE · Rechazar (estado = rechazada + motivo). PostgreSQL no se toca.
# =====================================================================
@require_POST
def rechazar(request, uuid):
    consultas.establecer_accion("UPDATE · Rechazar recepción (solo MongoDB)")
    motivo = (request.POST.get("motivo") or "").strip()
    if not motivo:
        messages.warning(request, "Indique el motivo del rechazo.")
        return redirect("muelle_detalle", uuid=uuid)
    try:
        r = recepciones_repo.rechazar(uuid, motivo)
    except PyMongoError as exc:
        error_mongo(request, exc)
        return redirect("muelle_detalle", uuid=uuid)
    if r.matched_count == 0:
        messages.warning(request, "No se rechazó: la recepción no está pendiente.")
    else:
        messages.success(request, "Recepción rechazada en MongoDB. La contabilidad (PostgreSQL) no se tocó.")
    return redirect("muelle_detalle", uuid=uuid)


# =====================================================================
# DELETE · solo pendiente o rechazada
# =====================================================================
@require_POST
def eliminar(request, uuid):
    consultas.establecer_accion("DELETE · Eliminar recepción (MongoDB)")
    try:
        r = recepciones_repo.eliminar(uuid)
    except PyMongoError as exc:
        error_mongo(request, exc)
        return redirect("muelle_detalle", uuid=uuid)
    if r.deleted_count == 0:
        documento = recepciones_repo.obtener(uuid)
        if documento and documento.get("estado") == "validada":
            messages.error(
                request,
                "No se puede eliminar: la recepción ya está validada y existe la compra oficial "
                f"#{documento.get('id_compra')} en PostgreSQL. El filtro del deleteOne "
                "(estado ∈ {pendiente, rechazada}) no la encontró: deleted_count = 0.",
            )
        else:
            messages.warning(request, "No se eliminó ningún documento (deleted_count = 0).")
        return redirect("muelle_detalle", uuid=uuid)
    messages.success(request, f"Recepción {uuid[:8]} eliminada (deleted_count = {r.deleted_count}).")
    return redirect("muelle_lista")


# =====================================================================
# Validador e índices de la colección (para la defensa)
# =====================================================================
def esquema_coleccion(request):
    consultas.establecer_accion("READ · Validador $jsonSchema e índices")
    contexto = {"info": esquema.info_coleccion()}
    return render(request, "core/muelle/esquema.html", contexto)


@require_POST
def invalido_demo(request):
    """CREATE (demo) · Un documento que incumple el validador $jsonSchema."""
    consultas.establecer_accion("CREATE (demo) · Documento inválido: lo rechaza el validador")
    try:
        uuid = recepciones_repo.insertar_invalido_demo()
        messages.warning(request, f"El documento {uuid[:8]} se insertó: revise el validador.")
    except PyMongoError as exc:
        error_mongo(request, exc, "Rechazado por MongoDB (validador $jsonSchema)")
    return redirect("muelle_esquema")
