"""Variables disponibles en todas las plantillas."""
from core import consultas
from core.utilidades import hoy


def pescapp(request):
    return {
        "usuarios": getattr(request, "usuarios", []),
        "usuario_actual": getattr(request, "usuario_actual", None),
        "accion_previa": getattr(request, "accion_previa", None),
        "consultas_pagina": consultas.consultas_actuales(),
        "accion_pagina": (consultas.estado_actual().accion if consultas.estado_actual() else ""),
        "hoy": hoy(),
    }
