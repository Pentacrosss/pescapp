"""
C · Catálogo · PostgreSQL · CRUD de productos; listar y crear
proveedores y clientes. Los rechazos (UNIQUE, clave foránea) los emite
el motor y se muestran con su mensaje real.
"""
from django.contrib import messages
from django.db import DatabaseError, IntegrityError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core import consultas
from core.bd import pg
from core.repositorios import catalogo_repo
from core.utilidades import a_entero
from core.views.comun import error_pg


# =====================================================================
# READ + CREATE · Productos
# =====================================================================
def productos(request):
    if request.method == "POST":
        # CREATE · INSERT ... RETURNING
        consultas.establecer_accion("CREATE · Producto (PostgreSQL)")
        try:
            nuevo = catalogo_repo.crear_producto(
                a_entero(request.POST.get("id_especie")),
                (request.POST.get("presentacion") or "").strip(),
                (request.POST.get("unidad") or "kg").strip(),
            )
            messages.success(
                request, f"Producto #{nuevo['id_producto']} «{nuevo['presentacion']}» creado (INSERT ... RETURNING)."
            )
        except IntegrityError as exc:
            if pg.describir_error(exc)["sqlstate"] == "23505":
                error_pg(request, exc, "Rechazado por PostgreSQL: ya existe esa especie + presentación (UNIQUE)")
            else:
                error_pg(request, exc)
        except DatabaseError as exc:
            error_pg(request, exc)
        return redirect("catalogo_productos")

    # READ · JOIN especie + uso en compras y ventas
    consultas.establecer_accion("READ · Productos JOIN especie (PostgreSQL)")
    contexto = {
        "productos": catalogo_repo.listar_productos(),
        "especies": catalogo_repo.listar_especies(),
    }
    return render(request, "core/catalogo/productos.html", contexto)


# =====================================================================
# UPDATE · Producto (presentación y unidad)
# =====================================================================
def producto_editar(request, id_producto):
    if request.method == "POST":
        consultas.establecer_accion("UPDATE · Producto (PostgreSQL)")
        try:
            fila = catalogo_repo.actualizar_producto(
                id_producto,
                (request.POST.get("presentacion") or "").strip(),
                (request.POST.get("unidad") or "kg").strip(),
            )
            if fila:
                messages.success(request, f"Producto #{id_producto} actualizado (UPDATE ... RETURNING).")
            else:
                messages.warning(request, "No existe el producto (0 filas afectadas).")
            return redirect("catalogo_productos")
        except IntegrityError as exc:
            error_pg(request, exc, "Rechazado por PostgreSQL: ya existe esa especie + presentación (UNIQUE)")
        except DatabaseError as exc:
            error_pg(request, exc)
        return redirect("catalogo_producto_editar", id_producto=id_producto)

    consultas.establecer_accion("READ · Producto a editar (PostgreSQL)")
    producto = catalogo_repo.obtener_producto(id_producto)
    if producto is None:
        raise Http404("Producto inexistente")
    return render(request, "core/catalogo/producto_editar.html", {"producto": producto})


# =====================================================================
# DELETE · Producto (la clave foránea lo impide si tiene movimientos)
# =====================================================================
@require_POST
def producto_eliminar(request, id_producto):
    consultas.establecer_accion("DELETE · Producto (PostgreSQL)")
    try:
        filas = catalogo_repo.eliminar_producto(id_producto)
        if filas:
            messages.success(request, f"Producto #{id_producto} eliminado ({filas} fila afectada).")
        else:
            messages.warning(request, "No existe el producto (0 filas afectadas).")
    except IntegrityError as exc:
        if pg.describir_error(exc)["sqlstate"] == "23503":
            error_pg(
                request,
                exc,
                "No se puede eliminar: el producto tiene compras o ventas asociadas. Motor",
            )
        else:
            error_pg(request, exc)
    return redirect("catalogo_productos")


# =====================================================================
# Proveedores y clientes: listar y crear
# =====================================================================
def proveedores(request):
    if request.method == "POST":
        consultas.establecer_accion("CREATE · Proveedor (PostgreSQL)")
        try:
            nuevo = catalogo_repo.crear_proveedor(
                (request.POST.get("nombre") or "").strip(),
                (request.POST.get("identificacion") or "").strip(),
                (request.POST.get("telefono") or "").strip(),
            )
            messages.success(request, f"Proveedor #{nuevo['id_proveedor']} creado.")
        except DatabaseError as exc:
            error_pg(request, exc)
        return redirect("catalogo_proveedores")
    consultas.establecer_accion("READ · Proveedores (PostgreSQL)")
    return render(request, "core/catalogo/proveedores.html", {"proveedores": catalogo_repo.listar_proveedores()})


def clientes(request):
    if request.method == "POST":
        consultas.establecer_accion("CREATE · Cliente (PostgreSQL)")
        try:
            nuevo = catalogo_repo.crear_cliente(
                (request.POST.get("nombre") or "").strip(),
                (request.POST.get("identificacion") or "").strip(),
                request.POST.get("tipo") or "minorista",
            )
            messages.success(request, f"Cliente #{nuevo['id_cliente']} creado.")
        except DatabaseError as exc:
            error_pg(request, exc)
        return redirect("catalogo_clientes")
    consultas.establecer_accion("READ · Clientes (PostgreSQL)")
    return render(request, "core/catalogo/clientes.html", {"clientes": catalogo_repo.listar_clientes()})
