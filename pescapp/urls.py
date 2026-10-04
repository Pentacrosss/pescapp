"""Rutas de pescAPP (agrupadas como se defenderán)."""
from django.urls import path

from core.views import catalogo, cierre, inicio, muelle, validacion, ventas

urlpatterns = [
    # G · Inicio, usuario actual, reinicio y bitácora
    path("", inicio.inicio, name="inicio"),
    path("usuario/", inicio.cambiar_usuario, name="cambiar_usuario"),
    path("reiniciar-demo/", inicio.reiniciar_demo, name="reiniciar_demo"),
    path("bitacora/", inicio.bitacora, name="bitacora"),
    # A · Muelle · MongoDB
    path("muelle/captura/", muelle.captura, name="muelle_captura"),
    path("muelle/api/sincronizar/", muelle.api_sincronizar, name="muelle_api_sincronizar"),
    path("muelle/", muelle.lista, name="muelle_lista"),
    path("muelle/pendientes/", muelle.pendientes, name="muelle_pendientes"),
    path("muelle/esquema/", muelle.esquema_coleccion, name="muelle_esquema"),
    path("muelle/esquema/invalido/", muelle.invalido_demo, name="muelle_invalido_demo"),
    path("muelle/<str:uuid>/", muelle.detalle, name="muelle_detalle"),
    path("muelle/<str:uuid>/corregir-linea/", muelle.corregir_linea, name="muelle_corregir_linea"),
    path("muelle/<str:uuid>/agregar-atributo/", muelle.agregar_atributo, name="muelle_agregar_atributo"),
    path("muelle/<str:uuid>/rechazar/", muelle.rechazar, name="muelle_rechazar"),
    path("muelle/<str:uuid>/eliminar/", muelle.eliminar, name="muelle_eliminar"),
    # B · Validación · MongoDB -> PostgreSQL
    path("validacion/", validacion.panel, name="validacion"),
    path("validacion/<str:uuid>/validar/", validacion.validar, name="validacion_validar"),
    path("validacion/<str:uuid>/forzar/", validacion.forzar, name="validacion_forzar"),
    path("validacion/<str:uuid>/desfasar/", validacion.desfasar, name="validacion_desfasar"),
    # C · Catálogo · PostgreSQL
    path("catalogo/productos/", catalogo.productos, name="catalogo_productos"),
    path("catalogo/productos/<int:id_producto>/editar/", catalogo.producto_editar, name="catalogo_producto_editar"),
    path("catalogo/productos/<int:id_producto>/eliminar/", catalogo.producto_eliminar, name="catalogo_producto_eliminar"),
    path("catalogo/proveedores/", catalogo.proveedores, name="catalogo_proveedores"),
    path("catalogo/clientes/", catalogo.clientes, name="catalogo_clientes"),
    # D · Ventas, cobros, pagos y saldos · PostgreSQL
    path("ventas/", ventas.lista, name="ventas_lista"),
    path("ventas/nueva/", ventas.nueva, name="ventas_nueva"),
    path("ventas/<int:id_venta>/", ventas.detalle, name="ventas_detalle"),
    path("ventas/<int:id_venta>/cobro/", ventas.cobro, name="ventas_cobro"),
    path("compras/", ventas.compras, name="compras_lista"),
    path("compras/<int:id_compra>/", ventas.compra_detalle, name="compras_detalle"),
    path("compras/<int:id_compra>/pago/", ventas.pago, name="compras_pago"),
    path("saldos/clientes/", ventas.saldos_clientes, name="saldos_clientes"),
    path("saldos/clientes/<int:id_cliente>/", ventas.saldo_cliente, name="saldo_cliente"),
    path("saldos/proveedores/", ventas.saldos_proveedores, name="saldos_proveedores"),
    path("saldos/proveedores/<int:id_proveedor>/", ventas.saldo_proveedor, name="saldo_proveedor"),
    # E · Cierre diario · PostgreSQL
    path("cierre/", cierre.cierre, name="cierre"),
    path("cierre/emitir/", cierre.emitir, name="cierre_emitir"),
    path("cierre/demo-venta/", cierre.demo_venta_dia_cerrado, name="cierre_demo_venta"),
]
