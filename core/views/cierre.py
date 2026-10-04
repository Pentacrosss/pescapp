"""E · Cierre diario · PostgreSQL (R6)."""
from decimal import Decimal

from django.contrib import messages
from django.db import DatabaseError, IntegrityError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core import consultas
from core.bd import pg
from core.repositorios import catalogo_repo, cierre_repo, ventas_repo
from core.utilidades import a_fecha, hoy
from core.views.comun import error_pg


def cierre(request):
    consultas.establecer_accion("READ · Cierres emitidos y movimientos por fecha")
    contexto = {
        "cierres": cierre_repo.listar_cierres(),
        "movimientos": cierre_repo.movimientos_por_fecha(),
        "fecha_sugerida": cierre_repo.fecha_sugerida() or hoy(),
        "ultima_cerrada": cierre_repo.ultima_fecha_cerrada(),
    }
    return render(request, "core/cierre/cierre.html", contexto)


# =====================================================================
# R6 · Emitir cierre: SELECT * FROM emitir_cierre(fecha, id_usuario)
# =====================================================================
@require_POST
def emitir(request):
    consultas.establecer_accion("R6 · Emitir cierre del día (función emitir_cierre)")
    fecha = a_fecha(request.POST.get("fecha"), hoy())
    try:
        c = cierre_repo.emitir_cierre(fecha, request.id_usuario)
        messages.success(
            request,
            f"Cierre #{c['id_cierre']} del {c['fecha']:%d/%m/%Y} emitido: compras ${c['total_compras']}, "
            f"ventas ${c['total_ventas']}, diferencia ${c['diferencia']}.",
        )
    except IntegrityError as exc:
        if pg.describir_error(exc)["sqlstate"] == "23505":
            error_pg(request, exc, "Rechazado por PostgreSQL: esa fecha ya tiene cierre (cierre_diario.fecha UNIQUE)")
        else:
            error_pg(request, exc)
    except DatabaseError as exc:
        error_pg(request, exc)
    return redirect("cierre")


# =====================================================================
# R6 · Demo: intentar una venta con fecha cerrada -> trigger
# =====================================================================
@require_POST
def demo_venta_dia_cerrado(request):
    consultas.establecer_accion("R6 · Demo: venta en día cerrado (trigger fn_bloquear_dia_cerrado)")
    fecha = a_fecha(request.POST.get("fecha")) or cierre_repo.ultima_fecha_cerrada() or hoy()
    cliente = catalogo_repo.listar_clientes()[0]
    producto = catalogo_repo.listar_productos()[0]
    try:
        venta = ventas_repo.registrar_venta(
            cliente["id_cliente"],
            request.id_usuario,
            fecha,
            [{"id_producto": producto["id_producto"], "peso_kg": Decimal("10.00"), "precio_kg": Decimal("5.00")}],
            nombre_transaccion="Demo · venta en día cerrado",
        )
        messages.warning(
            request,
            f"El {fecha:%d/%m/%Y} no tiene cierre: la venta #{venta['id_venta']} se registró normalmente.",
        )
    except DatabaseError as exc:
        error_pg(request, exc, "Rechazado por PostgreSQL (trigger fn_bloquear_dia_cerrado)")
    return redirect("cierre")
