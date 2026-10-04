"""
D · Ventas, cobros, pagos y saldos · PostgreSQL (R4, R5).
"""
from django.contrib import messages
from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core import consultas
from core.repositorios import catalogo_repo, compras_repo, ventas_repo
from core.utilidades import a_decimal, a_entero, a_fecha, hoy
from core.views.comun import error_pg

METODOS = ["efectivo", "transferencia"]


# =====================================================================
# READ · Ventas
# =====================================================================
def lista(request):
    consultas.establecer_accion("READ · Ventas con cobros (PostgreSQL)")
    return render(request, "core/ventas/lista.html", {"ventas": ventas_repo.listar_ventas()})


# =====================================================================
# CREATE · R4 · Registrar venta (transacción) con cobro inicial parcial
# =====================================================================
def _leer_lineas(post) -> list[dict]:
    lineas = []
    for id_producto, peso, precio in zip(
        post.getlist("id_producto"), post.getlist("peso_kg"), post.getlist("precio_kg")
    ):
        if not (id_producto and peso and precio):
            continue
        lineas.append(
            {
                "id_producto": a_entero(id_producto),
                "peso_kg": a_decimal(peso),
                "precio_kg": a_decimal(precio),
            }
        )
    return lineas


def nueva(request):
    lineas_previas = []
    valores = {"fecha": hoy().isoformat(), "id_cliente": "", "cobro_inicial": "", "metodo": "efectivo"}
    if request.method == "POST":
        consultas.establecer_accion("R4 · Registrar venta con cobro inicial (transacción)")
        lineas = _leer_lineas(request.POST)
        valores = {
            "fecha": request.POST.get("fecha") or hoy().isoformat(),
            "id_cliente": request.POST.get("id_cliente", ""),
            "cobro_inicial": request.POST.get("cobro_inicial", ""),
            "metodo": request.POST.get("metodo", "efectivo"),
        }
        lineas_previas = [
            {"id_producto": l["id_producto"], "peso_kg": str(l["peso_kg"]), "precio_kg": str(l["precio_kg"])}
            for l in lineas
        ]
        if not lineas:
            messages.warning(request, "Agregue al menos una línea con producto, peso y precio.")
        else:
            try:
                venta = ventas_repo.registrar_venta(
                    a_entero(valores["id_cliente"]),
                    request.id_usuario,
                    a_fecha(valores["fecha"], hoy()),
                    lineas,
                    cobro_inicial=a_decimal(valores["cobro_inicial"]),
                    metodo_cobro=valores["metodo"],
                )
                messages.success(
                    request,
                    f"Venta #{venta['id_venta']} registrada en una transacción: total ${venta['total']} "
                    f"(Σ subtotales calculada por el motor), estado {venta['estado']}.",
                )
                return redirect("ventas_detalle", id_venta=venta["id_venta"])
            except DatabaseError as exc:
                error_pg(request, exc, "Rechazado por PostgreSQL (se revirtió toda la venta)")
    else:
        consultas.establecer_accion("READ · Formulario de venta (catálogo)")

    contexto = {
        "clientes": catalogo_repo.listar_clientes(),
        "productos": catalogo_repo.listar_productos(),
        "valores": valores,
        "lineas_previas": lineas_previas,
        "metodos": METODOS,
    }
    return render(request, "core/ventas/nueva.html", contexto)


# =====================================================================
# READ · Detalle de venta + cuadre (total = Σ detalle)
# =====================================================================
def detalle(request, id_venta):
    consultas.establecer_accion("READ · Detalle de venta, cobros y cuadre")
    venta = ventas_repo.obtener_venta(id_venta)
    if venta is None:
        raise Http404("Venta inexistente")
    contexto = {
        "venta": venta,
        "detalle": ventas_repo.detalle_de_venta(id_venta),
        "cobros": ventas_repo.cobros_de_venta(id_venta),
        "cuadre": ventas_repo.cuadre_venta(id_venta),
        "saldo": venta["total"] - venta["cobrado"],
        "metodos": METODOS,
    }
    return render(request, "core/ventas/detalle.html", contexto)


# =====================================================================
# CREATE · R4 · Cobro posterior (el trigger rechaza montos > saldo)
# =====================================================================
@require_POST
def cobro(request, id_venta):
    consultas.establecer_accion("R4 · Registrar cobro (transacción)")
    try:
        r = ventas_repo.registrar_cobro(
            id_venta,
            a_fecha(request.POST.get("fecha"), hoy()),
            a_decimal(request.POST.get("monto")),
            request.POST.get("metodo") or "efectivo",
        )
        texto = f"Cobro #{r['id_cobro']} registrado."
        if r["cobrada"]:
            texto += " Los cobros alcanzaron el total: la venta quedó 'cobrada'."
        messages.success(request, texto)
    except DatabaseError as exc:
        error_pg(request, exc)
    return redirect("ventas_detalle", id_venta=id_venta)


# =====================================================================
# Compras (nacen de recepciones validadas) y pagos a proveedores
# =====================================================================
def compras(request):
    consultas.establecer_accion("READ · Compras oficiales con pagos (PostgreSQL)")
    return render(request, "core/ventas/compras.html", {"compras": compras_repo.listar_compras()})


def compra_detalle(request, id_compra):
    consultas.establecer_accion("READ · Detalle de compra y pagos")
    compra = compras_repo.obtener_compra(id_compra)
    if compra is None:
        raise Http404("Compra inexistente")
    contexto = {
        "compra": compra,
        "detalle": compras_repo.detalle_de_compra(id_compra),
        "pagos": compras_repo.pagos_de_compra(id_compra),
        "saldo": compra["total"] - compra["pagado"],
        "metodos": METODOS,
    }
    return render(request, "core/ventas/compra_detalle.html", contexto)


@require_POST
def pago(request, id_compra):
    consultas.establecer_accion("Registrar pago a proveedor (transacción)")
    try:
        r = compras_repo.registrar_pago(
            id_compra,
            a_fecha(request.POST.get("fecha"), hoy()),
            a_decimal(request.POST.get("monto")),
            request.POST.get("metodo") or "efectivo",
        )
        texto = f"Pago #{r['id_pago']} registrado."
        if r["pagada"]:
            texto += " Los pagos alcanzaron el total: la compra quedó 'pagada'."
        messages.success(request, texto)
    except DatabaseError as exc:
        error_pg(request, exc)
    return redirect("compras_detalle", id_compra=id_compra)


# =====================================================================
# READ · R5 · Saldos (vistas v_saldo_cliente y v_saldo_proveedor)
# =====================================================================
def saldos_clientes(request):
    consultas.establecer_accion("R5 · Saldos de clientes (v_saldo_cliente)")
    return render(request, "core/ventas/saldos_clientes.html", {"saldos": ventas_repo.saldos_clientes()})


def saldo_cliente(request, id_cliente):
    consultas.establecer_accion("R5 · Saldo de un cliente (valor oficial del momento)")
    saldo = ventas_repo.saldo_cliente(id_cliente)
    if saldo is None:
        raise Http404("Cliente inexistente")
    contexto = {"saldo": saldo, "ventas": ventas_repo.ventas_de_cliente(id_cliente)}
    return render(request, "core/ventas/saldo_cliente.html", contexto)


def saldos_proveedores(request):
    consultas.establecer_accion("R5 · Saldos de proveedores (v_saldo_proveedor)")
    return render(request, "core/ventas/saldos_proveedores.html", {"saldos": ventas_repo.saldos_proveedores()})


def saldo_proveedor(request, id_proveedor):
    consultas.establecer_accion("R5 · Saldo de un proveedor (valor oficial del momento)")
    saldo = ventas_repo.saldo_proveedor(id_proveedor)
    if saldo is None:
        raise Http404("Proveedor inexistente")
    contexto = {"saldo": saldo, "compras": ventas_repo.compras_de_proveedor(id_proveedor)}
    return render(request, "core/ventas/saldo_proveedor.html", contexto)
