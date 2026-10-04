"""Utilidades de conversión compartidas (números, fechas)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.utils import timezone

CENTAVO = Decimal("0.01")


def a_decimal(valor, por_defecto: Decimal | None = None) -> Decimal | None:
    """Texto o número -> Decimal con 2 decimales (redondeo comercial)."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return por_defecto
    try:
        return Decimal(str(valor).replace(",", ".")).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return por_defecto


def a_entero(valor, por_defecto: int | None = None) -> int | None:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return por_defecto


def a_fecha(valor, por_defecto: date | None = None) -> date | None:
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor).strip())
    except (TypeError, ValueError):
        return por_defecto


def hoy() -> date:
    """Fecha local (America/Guayaquil)."""
    return timezone.localdate()


def fecha_local(momento: datetime) -> date:
    """Fecha local de un instante (p. ej. capturado_en en UTC)."""
    return timezone.localtime(momento).date()


def rango_utc_del_dia(fecha: date) -> tuple[datetime, datetime]:
    """[00:00, 24:00) del día local expresado en UTC (para MongoDB)."""
    zona = timezone.get_current_timezone()
    inicio = datetime.combine(fecha, time.min, tzinfo=zona)
    fin = inicio + timedelta(days=1)
    return inicio.astimezone(dt_timezone.utc), fin.astimezone(dt_timezone.utc)
