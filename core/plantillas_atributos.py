"""
R2 · Plantillas de atributos por especie (solo para armar el formulario).

MongoDB NO valida estos campos: el validador $jsonSchema exige que
"atributos" sea un objeto, pero no fija sus claves. Por eso cada especie
trae atributos distintos y se pueden agregar atributos libres (clave/
valor) sin cambiar el esquema.
"""

PLANTILLAS_ATRIBUTOS = {
    "Dorado": [
        {"clave": "talla", "etiqueta": "Talla", "tipo": "opciones",
         "opciones": ["pequeño", "mediano", "grande"]},
        {"clave": "calidad", "etiqueta": "Calidad", "tipo": "opciones",
         "opciones": ["A", "B", "C"]},
        {"clave": "temperatura_c", "etiqueta": "Temperatura (°C)", "tipo": "numero"},
    ],
    "Camarón": [
        {"clave": "calibre", "etiqueta": "Calibre", "tipo": "opciones",
         "opciones": ["21-25", "26-30", "31-40", "41-50"]},
        {"clave": "calidad", "etiqueta": "Calidad", "tipo": "opciones",
         "opciones": ["A", "B", "C"]},
    ],
    "Atún": [
        {"clave": "peso_pieza_kg", "etiqueta": "Peso por pieza (kg)", "tipo": "numero"},
        {"clave": "grado", "etiqueta": "Grado", "tipo": "opciones",
         "opciones": ["1", "2", "3"]},
        {"clave": "temperatura_c", "etiqueta": "Temperatura (°C)", "tipo": "numero"},
    ],
}


def convertir_valor(valor: str):
    """Convierte el texto de un atributo libre a número cuando corresponde."""
    texto = (valor or "").strip()
    try:
        if texto.lstrip("-").isdigit():
            return int(texto)
        return float(texto.replace(",", "."))
    except ValueError:
        return texto
