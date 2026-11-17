
import json
from pathlib import Path

from prompts_llm import (
    INSTRUCCIONES,
    cargar_desarrollo,
    ejemplo_json,
)

BASE = Path(__file__).resolve().parent.parent

PROTOCOLO = (
    BASE / "results/llm_dev/"
    "protocolo_fewshot_fijo.json"
)


def cargar_protocolo(desarrollo):
    with PROTOCOLO.open(encoding="utf-8") as archivo:
        protocolo = json.load(archivo)

    if protocolo["version"] != "fewshot_fijo_v1":
        raise ValueError("Version de protocolo incorrecta")

    if len(protocolo["ids_ejemplos"]) != 3:
        raise ValueError("Deben existir tres ejemplos")

    if len(set(protocolo["ids_ejemplos"])) != 3:
        raise ValueError("Ejemplos duplicados")

    por_id = {e["event_id"]: e for e in desarrollo}

    if len(por_id) != 158:
        raise ValueError("Dataset dev inconsistente")

    ejemplos = [
        por_id[identificador]
        for identificador in protocolo["ids_ejemplos"]
    ]

    niveles = [
        e["etiqueta"]["nivel"] for e in ejemplos
    ]

    if niveles != ["INFO", "MEDIO", "ALTO"]:
        raise ValueError("Niveles de ejemplos incorrectos")

    ids_evaluacion = protocolo["ids_evaluacion"]

    if (
        len(ids_evaluacion) != 148
        or len(set(ids_evaluacion)) != 148
    ):
        raise ValueError("Evaluacion debe tener 148 IDs")

    grupos_reservados = {
        (e["etiqueta"]["fuente"], e["etiqueta"]["grupo"])
        for e in ejemplos
    }

    esperados = {
        e["event_id"]
        for e in desarrollo
        if (
            e["etiqueta"]["fuente"],
            e["etiqueta"]["grupo"],
        ) not in grupos_reservados
    }

    if set(ids_evaluacion) != esperados:
        raise ValueError(
            "La particion no coincide con los grupos reservados"
        )

    return protocolo, ejemplos


def construir_fewshot_fijo(evento, ejemplos):
    contenido = (
        INSTRUCCIONES
        + "\n\nEJEMPLOS RESUELTOS DE DESARROLLO:"
    )

    for numero, ejemplo in enumerate(ejemplos, 1):
        respuesta = ejemplo_json(ejemplo["etiqueta"])

        contenido += (
            f"\n\nEjemplo {numero}:\n"
            f"{ejemplo['texto']}\n"
            "Respuesta:\n"
            + json.dumps(
                respuesta, ensure_ascii=False
            )
        )

    contenido += (
        "\n\nClasifica el nuevo evento utilizando "
        "los criterios anteriores. "
        "No copies automaticamente las respuestas "
        "de los ejemplos."
        "\n\nEVENTO A CLASIFICAR:\n"
        + evento["texto"]
        + "\n\nRESPUESTA JSON:"
    )

    return contenido


if __name__ == "__main__":
    desarrollo = cargar_desarrollo()
    protocolo, ejemplos = cargar_protocolo(desarrollo)

    por_id = {e["event_id"]: e for e in desarrollo}
    ids_ejemplos = set(protocolo["ids_ejemplos"])

    for identificador in protocolo["ids_evaluacion"]:
        evento = por_id[identificador]

        assert identificador not in ids_ejemplos

        prompt = construir_fewshot_fijo(
            evento, ejemplos
        )

        assert prompt.endswith("RESPUESTA JSON:")

    print("Ejemplos fijos:", protocolo["ids_ejemplos"])
    print(
        "Eventos de evaluacion:",
        len(protocolo["ids_evaluacion"])
    )
    print("Filtracion de ejemplos: 0")
    print("PROMPTS FEW-SHOT FIJOS: OK")

