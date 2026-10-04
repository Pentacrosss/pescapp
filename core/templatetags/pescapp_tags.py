"""Filtros de plantilla de pescAPP."""
from decimal import Decimal, InvalidOperation

from django import template

from core.bd.mongo import a_mongosh

register = template.Library()


@register.filter
def dinero(valor):
    """1234.5 -> $1,234.50 · -20 -> -$20.00"""
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return valor
    signo = "-" if numero < 0 else ""
    return f"{signo}${abs(numero):,.2f}"


@register.filter
def num(valor, decimales=2):
    try:
        return f"{Decimal(str(valor)):,.{int(decimales)}f}"
    except (InvalidOperation, ValueError, TypeError):
        return valor


@register.filter
def corto(uuid):
    return str(uuid)[:8] if uuid else ""


@register.filter
def mongosh(valor):
    return a_mongosh(valor)


@register.filter
def item(diccionario, clave):
    try:
        return diccionario.get(clave)
    except AttributeError:
        return None


@register.filter
def total_kg(documento):
    try:
        return sum(float(l.get("peso_kg", 0)) for l in documento.get("lineas", []))
    except (TypeError, ValueError):
        return ""


@register.filter
def total_estimado(documento):
    try:
        return sum(
            round(float(l.get("peso_kg", 0)) * float(l.get("precio_kg", 0)), 2)
            for l in documento.get("lineas", [])
        )
    except (TypeError, ValueError):
        return ""


@register.filter
def subtotal(linea):
    try:
        return round(float(linea.get("peso_kg", 0)) * float(linea.get("precio_kg", 0)), 2)
    except (TypeError, ValueError):
        return ""


@register.filter
def especies(documento):
    vistas = []
    for linea in documento.get("lineas", []):
        especie = linea.get("especie")
        if especie and especie not in vistas:
            vistas.append(especie)
    return ", ".join(vistas)


@register.filter
def color_estado(estado):
    return {
        "pendiente": "warning",
        "validada": "success",
        "rechazada": "danger",
        "pendiente_pago": "warning",
        "pagada": "success",
        "pendiente_cobro": "warning",
        "cobrada": "success",
        "anulada": "secondary",
    }.get(estado, "secondary")
