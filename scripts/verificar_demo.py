#!/usr/bin/env python
"""
Verificación automática de pescAPP (Momento 2).

Recorre, a través de las MISMAS vistas HTTP que usa la interfaz
(django.test.Client), el CRUD de cada motor y las cinco operaciones
clave del Momento 1, y comprueba el resultado directamente en
PostgreSQL y MongoDB. Imprime PASS/FAIL por cada verificación.

Uso:
    docker compose exec web python scripts/verificar_demo.py
    python scripts/verificar_demo.py              (sin Docker, con .env)

Opciones:
    --sin-reinicio   no reinicia los datos de demo al inicio ni al final
                     (por defecto se reinician antes y después).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pescapp.settings")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from core.bd import mongo  # noqa: E402
from core.servicios import semilla  # noqa: E402
from core.utilidades import hoy  # noqa: E402

RESULTADOS: list[tuple[str, bool]] = []
RESPUESTAS_ACCION: list[tuple[str, str]] = []


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------
def verificar(nombre: str, condicion, detalle: str = "") -> bool:
    ok = bool(condicion)
    RESULTADOS.append((nombre, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {nombre}" + (f"  — {detalle}" if detalle else ""))
    return ok


def seccion(titulo: str) -> None:
    print(f"\n=== {titulo} ===")


def sql_uno(sql: str, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def doc_mongo(uuid_recepcion: str):
    return mongo.coleccion().find_one({"_id": uuid_recepcion})


def post(cliente: Client, url: str, datos: dict, nombre: str) -> str:
    """POST de formulario -> sigue la redirección -> HTML final."""
    r = cliente.post(url, datos, follow=True)
    html = r.content.decode("utf-8")
    RESPUESTAS_ACCION.append((nombre, html))
    return html


def api(cliente: Client, documentos: list[dict]) -> dict:
    r = cliente.post(
        "/muelle/api/sincronizar/",
        data=json.dumps({"recepciones": documentos, "titulo": "verificar_demo"}),
        content_type="application/json",
    )
    return r.json()


def nueva_recepcion(lineas: list[dict], id_proveedor: int = 2) -> dict:
    return {
        "_id": str(uuid.uuid4()),
        "id_usuario": 3,
        "id_proveedor": id_proveedor,
        "capturado_en": timezone.now().isoformat(),
        "lineas": lineas,
        "observaciones": "Creada por verificar_demo.py",
    }


# ---------------------------------------------------------------------
# A · MongoDB · CRUD de recepciones + operaciones 1 y 2
# ---------------------------------------------------------------------
def probar_mongo(c: Client) -> dict:
    seccion("A · MongoDB · CRUD de recepciones (R1, R2)")
    doc_a = nueva_recepcion(
        [
            {"id_producto": 1, "especie": "Dorado", "peso_kg": 142.5, "precio_kg": 3.10,
             "atributos": {"talla": "grande", "calidad": "A", "temperatura_c": 2.1}},
            {"id_producto": 3, "especie": "Camarón", "peso_kg": 60, "precio_kg": 5.40,
             "atributos": {"calibre": "31-40", "calidad": "B"}},
        ]
    )
    doc_b = nueva_recepcion(
        [
            {"id_producto": 5, "especie": "Atún", "peso_kg": 210, "precio_kg": 3.25,
             "atributos": {"peso_pieza_kg": 32.5, "grado": "1", "temperatura_c": 0.8, "embarcacion": "Fibra San Pedro"}},
        ],
        id_proveedor=4,
    )

    # CREATE · operación 1: atributos distintos por especie
    total_antes = mongo.coleccion().count_documents({})
    respuesta = api(c, [doc_a, doc_b])
    acciones = [r["accion"] for r in respuesta["resultados"]]
    verificar("CREATE Mongo · upsert inserta 2 recepciones nuevas", acciones == ["insertada", "insertada"], str(acciones))
    verificar(
        "CREATE Mongo · el total de documentos aumentó en 2",
        mongo.coleccion().count_documents({}) == total_antes + 2,
    )
    guardado_a = doc_mongo(doc_a["_id"])
    guardado_b = doc_mongo(doc_b["_id"])
    verificar(
        "R2 · cada especie guarda atributos distintos sin cambiar el esquema",
        set(guardado_a["lineas"][0]["atributos"]) == {"talla", "calidad", "temperatura_c"}
        and set(guardado_a["lineas"][1]["atributos"]) == {"calibre", "calidad"}
        and "peso_pieza_kg" in guardado_b["lineas"][0]["atributos"],
    )
    verificar(
        "Panel · la respuesta JSON incluye los comandos MongoDB ejecutados",
        any("updateOne" in q["sentencia"] for q in respuesta["consultas"]),
    )

    # Operación 1 · reenviar la misma recepción no la duplica
    total_antes = mongo.coleccion().count_documents({})
    reenvio = api(c, [doc_a])["resultados"][0]
    verificar(
        "R1 · reenviar el mismo UUID no duplica (total igual, reenvios = 1)",
        reenvio["accion"] == "actualizada"
        and reenvio["total_antes"] == reenvio["total_despues"] == total_antes
        and doc_mongo(doc_a["_id"])["reenvios"] == 1,
        f"pasos={[(p['matched_count'], p['modified_count'], p['upserted_id']) for p in reenvio['pasos']]}",
    )

    # READ
    html = c.get("/muelle/", {"estado": "pendiente"}).content.decode()
    verificar("READ Mongo · la lista filtrada por estado muestra la recepción", doc_a["_id"][:8] in html)
    html = c.get(f"/muelle/{doc_a['_id']}/").content.decode()
    verificar("READ Mongo · el detalle muestra atributos distintos por línea", "calibre" in html and "talla" in html)
    html = c.get("/muelle/", {"especie": "Atún", "plan": "1"}).content.decode()
    verificar("READ Mongo · filtro por especie + plan de consulta", doc_b["_id"][:8] in html and "Plan de consulta" in html)

    # Operación 2 · pendientes del día con índice
    html = c.get("/muelle/pendientes/", {"plan": "1"}).content.decode()
    verificar(
        "R1 · pendientes del día usan IXSCAN sobre estado_1_capturado_en_1",
        doc_a["_id"][:8] in html and "IXSCAN" in html and "estado_1_capturado_en_1" in html,
    )

    # UPDATE · corregir peso y agregar atributo
    post(c, f"/muelle/{doc_a['_id']}/corregir-linea/", {"indice": 0, "peso_kg": "150.5"}, "UPDATE Mongo")
    verificar("UPDATE Mongo · $set corrige el peso de una línea", doc_mongo(doc_a["_id"])["lineas"][0]["peso_kg"] == 150.5)
    post(c, f"/muelle/{doc_a['_id']}/agregar-atributo/", {"indice": 1, "clave": "lote", "valor": "L-0457"}, "UPDATE Mongo R2")
    verificar(
        "UPDATE Mongo · R2 · se agrega el atributo «lote» sin tocar el esquema",
        doc_mongo(doc_a["_id"])["lineas"][1]["atributos"].get("lote") == "L-0457",
    )

    # Validador $jsonSchema
    total_antes = mongo.coleccion().count_documents({})
    html = post(c, "/muelle/esquema/invalido/", {}, "Validador")
    verificar(
        "Validador $jsonSchema rechaza un documento inválido (mensaje del motor)",
        "Document failed validation" in html and mongo.coleccion().count_documents({}) == total_antes,
    )

    # DELETE
    doc_c = nueva_recepcion(
        [{"id_producto": 2, "especie": "Dorado", "peso_kg": 20, "precio_kg": 4.0, "atributos": {"talla": "mediano"}}]
    )
    api(c, [doc_c])
    post(c, f"/muelle/{doc_c['_id']}/eliminar/", {}, "DELETE Mongo")
    verificar("DELETE Mongo · se elimina una recepción pendiente", doc_mongo(doc_c["_id"]) is None)

    # UPDATE · rechazar (PostgreSQL no se toca)
    compras_antes = sql_uno("SELECT COUNT(*) FROM compra")[0]
    post(c, f"/muelle/{doc_b['_id']}/rechazar/", {"motivo": "Hielo insuficiente"}, "Rechazar")
    verificar(
        "UPDATE Mongo · rechazar cambia el estado y no toca PostgreSQL",
        doc_mongo(doc_b["_id"])["estado"] == "rechazada"
        and sql_uno("SELECT COUNT(*) FROM compra")[0] == compras_antes,
    )
    return {"a": doc_a["_id"], "b": doc_b["_id"]}


# ---------------------------------------------------------------------
# B · PostgreSQL · CRUD de productos
# ---------------------------------------------------------------------
def probar_productos(c: Client) -> None:
    seccion("C · PostgreSQL · CRUD de productos")
    post(c, "/catalogo/productos/", {"id_especie": 1, "presentacion": "en rodajas", "unidad": "kg"}, "CREATE producto")
    fila = sql_uno("SELECT id_producto FROM producto WHERE id_especie = 1 AND presentacion = 'en rodajas'")
    verificar("CREATE PG · INSERT ... RETURNING crea el producto", fila is not None)
    id_producto = fila[0] if fila else 0

    html = post(c, "/catalogo/productos/", {"id_especie": 1, "presentacion": "en rodajas", "unidad": "kg"}, "CREATE duplicado")
    verificar(
        "CREATE PG · repetir especie + presentación lo rechaza el UNIQUE",
        "duplicate key value" in html
        and sql_uno("SELECT COUNT(*) FROM producto WHERE id_especie = 1 AND presentacion = 'en rodajas'")[0] == 1,
    )

    html = c.get("/catalogo/productos/").content.decode()
    verificar("READ PG · la lista (JOIN especie) muestra el producto", "en rodajas" in html)

    post(c, f"/catalogo/productos/{id_producto}/editar/", {"presentacion": "rodajas finas", "unidad": "lb"}, "UPDATE producto")
    verificar(
        "UPDATE PG · se actualizan presentación y unidad",
        sql_uno("SELECT presentacion, unidad FROM producto WHERE id_producto = %s", [id_producto]) == ("rodajas finas", "lb"),
    )

    post(c, f"/catalogo/productos/{id_producto}/eliminar/", {}, "DELETE producto")
    verificar(
        "DELETE PG · se elimina un producto sin movimientos",
        sql_uno("SELECT COUNT(*) FROM producto WHERE id_producto = %s", [id_producto])[0] == 0,
    )

    html = post(c, "/catalogo/productos/1/eliminar/", {}, "DELETE con FK")
    verificar(
        "DELETE PG · la clave foránea impide borrar un producto con compras/ventas",
        "No se puede eliminar" in html
        and "foreign key" in html
        and sql_uno("SELECT COUNT(*) FROM producto WHERE id_producto = 1")[0] == 1,
    )


# ---------------------------------------------------------------------
# Operación 3 · R3 · validación transaccional y doble contabilización
# ---------------------------------------------------------------------
def probar_validacion(c: Client, uuids: dict) -> int:
    seccion("B · Integración · Operación 3 (R3)")
    uuid_a = uuids["a"]
    compras_antes = sql_uno("SELECT COUNT(*) FROM compra")[0]
    post(c, f"/validacion/{uuid_a}/validar/", {}, "Validar")
    fila = sql_uno("SELECT id_compra, total, estado FROM compra WHERE uuid_recepcion = %s", [uuid_a])
    verificar("R3 · validar crea la compra con uuid_recepcion = _id", fila is not None and fila[2] == "pendiente_pago")
    id_compra = fila[0] if fila else 0
    suma = sql_uno("SELECT SUM(subtotal), COUNT(*) FROM detalle_compra WHERE id_compra = %s", [id_compra])
    verificar(
        "R3 · total de la compra = Σ subtotales (ROUND(peso × precio, 2))",
        fila is not None and fila[1] == suma[0] and suma[1] == 2 and fila[1] == Decimal("790.55"),  # 150.5 × 3.10 + 60 × 5.40
        f"total={fila[1] if fila else None} Σ={suma[0]}",
    )
    documento = doc_mongo(uuid_a)
    verificar(
        "R3 · MongoDB queda 'validada' con id_compra y validado_en",
        documento["estado"] == "validada" and documento.get("id_compra") == id_compra and documento.get("validado_en"),
    )

    html = post(c, f"/validacion/{uuid_a}/forzar/", {}, "Forzar revalidación")
    verificar(
        "R3 · forzar revalidación: PostgreSQL la rechaza (UNIQUE uuid_recepcion)",
        "ya fue contabilizada" in html
        and "duplicate key value" in html
        and sql_uno("SELECT COUNT(*) FROM compra")[0] == compras_antes + 1,
    )

    post(c, f"/validacion/{uuid_a}/desfasar/", {}, "Desfasar")
    html = post(c, f"/validacion/{uuid_a}/validar/", {}, "Validar desfasada")
    documento = doc_mongo(uuid_a)
    verificar(
        "R3 · MongoDB desfasado se reconcilia a 'validada' sin crear otra compra",
        "reconcili" in html
        and documento["estado"] == "validada"
        and documento.get("id_compra") == id_compra
        and sql_uno("SELECT COUNT(*) FROM compra")[0] == compras_antes + 1,
    )

    verificar(
        "R3 · una recepción rechazada no genera compra",
        sql_uno("SELECT COUNT(*) FROM compra WHERE uuid_recepcion = %s", [uuids["b"]])[0] == 0,
    )
    html = post(c, f"/muelle/{uuid_a}/eliminar/", {}, "DELETE validada")
    verificar(
        "DELETE Mongo · una recepción validada no se puede borrar",
        doc_mongo(uuid_a) is not None and "No se puede eliminar" in html,
    )
    return id_compra


# ---------------------------------------------------------------------
# Operación 4 · R4/R5 · venta con cobro parcial y saldo del cliente
# ---------------------------------------------------------------------
def probar_ventas(c: Client, id_compra: int) -> None:
    seccion("D · PostgreSQL · Operación 4 (R4, R5)")
    id_cliente = 2
    saldo_antes = sql_uno("SELECT saldo_pendiente FROM v_saldo_cliente WHERE id_cliente = %s", [id_cliente])[0]
    ventas_antes = sql_uno("SELECT COALESCE(MAX(id_venta), 0) FROM venta")[0]
    post(
        c,
        "/ventas/nueva/",
        {
            "id_cliente": id_cliente,
            "fecha": hoy().isoformat(),
            "id_producto": ["1", "3"],
            "peso_kg": ["10.50", "4"],
            "precio_kg": ["5.25", "8.10"],
            "cobro_inicial": "40.00",
            "metodo": "efectivo",
        },
        "Registrar venta",
    )
    venta = sql_uno("SELECT id_venta, total, estado FROM venta WHERE id_venta > %s ORDER BY id_venta DESC LIMIT 1", [ventas_antes])
    verificar(
        "R4 · venta registrada en una transacción con cobro parcial",
        venta is not None and venta[1] == Decimal("87.53") and venta[2] == "pendiente_cobro",
        f"venta={venta}",
    )
    id_venta = venta[0] if venta else 0
    cuadre = sql_uno(
        "SELECT v.total = SUM(d.subtotal) FROM venta v JOIN detalle_venta d USING (id_venta) "
        "WHERE v.id_venta = %s GROUP BY v.total",
        [id_venta],
    )
    verificar("R4 · el total cuadra con el detalle (total = Σ subtotal)", cuadre is not None and cuadre[0] is True)

    saldo_despues = sql_uno("SELECT saldo_pendiente FROM v_saldo_cliente WHERE id_cliente = %s", [id_cliente])[0]
    html = c.get(f"/saldos/clientes/{id_cliente}/").content.decode()
    verificar(
        "R5 · el saldo del cliente (v_saldo_cliente) sube en total − cobro",
        saldo_despues - saldo_antes == Decimal("47.53") and f"{saldo_despues:,.2f}" in html,
        f"{saldo_antes} → {saldo_despues}",
    )

    html = post(c, f"/ventas/{id_venta}/cobro/", {"fecha": hoy().isoformat(), "monto": "100.00", "metodo": "efectivo"}, "Cobro excesivo")
    verificar(
        "R4 · un cobro mayor que el saldo lo rechaza el trigger",
        "supera el saldo pendiente" in html
        and sql_uno("SELECT SUM(monto) FROM cobro WHERE id_venta = %s", [id_venta])[0] == Decimal("40.00"),
    )
    post(c, f"/ventas/{id_venta}/cobro/", {"fecha": hoy().isoformat(), "monto": "47.53", "metodo": "transferencia"}, "Cobro final")
    verificar(
        "R4 · al completar los cobros la venta queda 'cobrada'",
        sql_uno("SELECT estado FROM venta WHERE id_venta = %s", [id_venta])[0] == "cobrada",
    )

    total_compra = sql_uno("SELECT total FROM compra WHERE id_compra = %s", [id_compra])[0]
    post(c, f"/compras/{id_compra}/pago/", {"fecha": hoy().isoformat(), "monto": str(total_compra), "metodo": "efectivo"}, "Pago")
    verificar(
        "R5 · pago completo a proveedor deja la compra 'pagada'",
        sql_uno("SELECT estado FROM compra WHERE id_compra = %s", [id_compra])[0] == "pagada",
    )
    html = c.get("/saldos/proveedores/").content.decode()
    verificar("R5 · la página de saldos de proveedores (v_saldo_proveedor) responde", "v_saldo_proveedor" in html)


# ---------------------------------------------------------------------
# Operación 5 · R6 · cierre diario y venta en día cerrado
# ---------------------------------------------------------------------
def probar_cierre(c: Client) -> None:
    seccion("E · PostgreSQL · Operación 5 (R6)")
    ayer = hoy() - timedelta(days=1)
    post(c, "/cierre/emitir/", {"fecha": ayer.isoformat()}, "Emitir cierre")
    cierre = sql_uno("SELECT total_compras, total_ventas, diferencia FROM cierre_diario WHERE fecha = %s", [ayer])
    esperado = sql_uno(
        "SELECT (SELECT COALESCE(SUM(total),0) FROM compra WHERE fecha = %s AND estado <> 'anulada'),"
        "       (SELECT COALESCE(SUM(total),0) FROM venta  WHERE fecha = %s AND estado <> 'anulada')",
        [ayer, ayer],
    )
    verificar(
        "R6 · emitir_cierre() suma compras/ventas y calcula la diferencia",
        cierre is not None and cierre[0] == esperado[0] and cierre[1] == esperado[1] and cierre[2] == esperado[1] - esperado[0],
        f"cierre={cierre}",
    )
    html = post(c, "/cierre/emitir/", {"fecha": ayer.isoformat()}, "Cierre repetido")
    verificar(
        "R6 · un segundo cierre de la misma fecha lo rechaza el UNIQUE",
        "duplicate key value" in html and sql_uno("SELECT COUNT(*) FROM cierre_diario WHERE fecha = %s", [ayer])[0] == 1,
    )
    ventas_antes = sql_uno("SELECT COUNT(*) FROM venta WHERE fecha = %s", [ayer])[0]
    html = post(c, "/cierre/demo-venta/", {"fecha": ayer.isoformat()}, "Venta en día cerrado")
    verificar(
        "R6 · una venta con fecha cerrada la rechaza el trigger fn_bloquear_dia_cerrado",
        "Día cerrado" in html and sql_uno("SELECT COUNT(*) FROM venta WHERE fecha = %s", [ayer])[0] == ventas_antes,
    )
    try:
        with connection.cursor() as cur:
            cur.execute("UPDATE compra SET total = total + 1 WHERE fecha = %s", [ayer])
        bloqueado = False
    except Exception as exc:  # noqa: BLE001
        bloqueado = "Día cerrado" in str(exc)
    verificar("R6 · el trigger también impide modificar una compra de un día cerrado", bloqueado)

    # Validar una recepción de un día cerrado: también la rechaza el trigger
    post(c, "/cierre/emitir/", {"fecha": hoy().isoformat()}, "Cierre de hoy")
    pendiente = mongo.coleccion().find_one({"estado": "pendiente"})
    html = post(c, f"/validacion/{pendiente['_id']}/validar/", {}, "Validar en día cerrado")
    verificar(
        "R6 · validar una recepción de un día cerrado: trigger + ROLLBACK, MongoDB sigue pendiente",
        "Día cerrado" in html
        and doc_mongo(pendiente["_id"])["estado"] == "pendiente"
        and sql_uno("SELECT COUNT(*) FROM compra WHERE uuid_recepcion = %s", [pendiente["_id"]])[0] == 0,
    )


# ---------------------------------------------------------------------
# F · Panel "Consulta ejecutada" y Bitácora
# ---------------------------------------------------------------------
def probar_panel(c: Client) -> None:
    seccion("F · Panel «Consulta ejecutada» y Bitácora")
    sin_panel = [n for n, html in RESPUESTAS_ACCION if 'id="panel-accion"' not in html]
    verificar(
        f"Panel · las {len(RESPUESTAS_ACCION)} acciones muestran «Consulta ejecutada»",
        not sin_panel,
        f"sin panel: {sin_panel}" if sin_panel else "",
    )
    errores_con_motor = [n for n, html in RESPUESTAS_ACCION if "error-motor" in html]
    verificar("Panel · los rechazos muestran el error devuelto por el motor", len(errores_con_motor) >= 6, f"{len(errores_con_motor)} con error del motor")
    html = c.get("/bitacora/").content.decode()
    verificar("Bitácora · lista operaciones de ambos motores", "badge-pg" in html and "badge-mongo" in html)


# ---------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sin-reinicio", action="store_true")
    args = parser.parse_args()

    if not args.sin_reinicio:
        print("Reiniciando datos de demo...")
        semilla.reiniciar_demo()

    cliente = Client()
    cliente.cookies["pescapp_usuario"] = "1"
    try:
        uuids = probar_mongo(cliente)
        probar_productos(cliente)
        id_compra = probar_validacion(cliente, uuids)
        probar_ventas(cliente, id_compra)
        probar_cierre(cliente)
        probar_panel(cliente)
    finally:
        if not args.sin_reinicio:
            print("\nRestaurando datos de demo...")
            semilla.reiniciar_demo()

    aprobadas = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\nResultado: {aprobadas}/{len(RESULTADOS)} PASS")
    return 0 if aprobadas == len(RESULTADOS) else 1


if __name__ == "__main__":
    sys.exit(main())
