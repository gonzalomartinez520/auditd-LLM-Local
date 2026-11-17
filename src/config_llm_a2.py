
# Configuracion comun del experimento LLM A2

URL_OLLAMA = "http://127.0.0.1:11434/api/generate"

MODELOS = [
    "qwen3:0.6b",
    "gemma3:1b",
]

ESTRATEGIAS = [
    "zero_shot",
    "few_shot",
    "chain_of_thought",
]

OPCIONES = {
    "temperature": 0,
    "seed": 42,
    "num_ctx": 4096,
    "num_predict": 256,
}

NIVELES = ["INFO", "BAJO", "MEDIO", "ALTO"]

TIPOS = [
    "actividad_normal",
    "anomalia_operativa",
    "autenticacion",
    "reconocimiento",
    "anomalia_privilegios",
    "acceso_sensible",
    "modificacion_configuracion",
    "otro",
]

ESQUEMA_RESPUESTA = {
    "type": "object",
    "properties": {
        "amenaza": {
            "type": "boolean",
        },
        "nivel": {
            "type": "string",
            "enum": NIVELES,
        },
        "tipo": {
            "type": "string",
            "enum": TIPOS,
        },
        "explicacion": {
            "type": "string",
        },
    },
    "required": [
        "amenaza",
        "nivel",
        "tipo",
        "explicacion",
    ],
    "additionalProperties": False,
}


def validar_prediccion(datos):
    if not isinstance(datos, dict):
        return False

    if set(datos) != {
        "amenaza", "nivel", "tipo", "explicacion"
    }:
        return False

    if type(datos["amenaza"]) is not bool:
        return False

    if datos["nivel"] not in NIVELES:
        return False

    if datos["tipo"] not in TIPOS:
        return False

    if not isinstance(datos["explicacion"], str):
        return False

    if not datos["explicacion"].strip():
        return False

    if datos["amenaza"] != (
        datos["nivel"] != "INFO"
    ):
        return False

    return True

