
import hashlib
import json
from collections import Counter
from pathlib import Path

from prompts_llm import cargar_desarrollo

BASE = Path(__file__).resolve().parent.parent
SALIDA = (
    BASE / "results/llm_dev/"
    "protocolo_fewshot_fijo.json"
)

# Fuentes conocidas exclusivamente del conjunto DEV.
# Elegimos un ejemplo de cada nivel presente.
FUENTES_EJEMPLOS = {
    "INFO": "E1",
    "MEDIO": "E2",
    "ALTO": "E5b",
}


def clave_grupo(evento):
    etiqueta = evento["etiqueta"]
    return (
        etiqueta["fuente"],
        etiqueta["grupo"],
    )


def main():
    if SALIDA.exists():
        raise SystemExit(
            "ERROR: el protocolo ya existe. "
            "No se sobrescribira."
        )

    desarrollo = cargar_desarrollo()
    ejemplos = []

    # Seleccion determinista, sin utilizar test.
    for nivel, fuente in FUENTES_EJEMPLOS.items():
        candidatos = [
            evento for evento in desarrollo
            if evento["etiqueta"]["fuente"] == fuente
            and evento["etiqueta"]["nivel"] == nivel
        ]

        if not candidatos:
            raise ValueError(
                f"Sin ejemplos para {nivel}"
            )

        candidatos.sort(
            key=lambda evento: (
                len(evento["texto"].encode("utf-8")),
                evento["event_id"],
            )
        )

        ejemplos.append(candidatos[0])

    grupos_reservados = {
        clave_grupo(e) for e in ejemplos
    }

    evaluacion = [
        e for e in desarrollo
        if clave_grupo(e) not in grupos_reservados
    ]

    ids_ejemplos = {
        e["event_id"] for e in ejemplos
    }

    ids_evaluacion = {
        e["event_id"] for e in evaluacion
    }

    if ids_ejemplos & ids_evaluacion:
        raise ValueError(
            "Filtracion de ejemplos en evaluacion"
        )

    if len(evaluacion) != len(ids_evaluacion):
        raise ValueError(
            "Identificadores duplicados"
        )

    if len(ejemplos) != 3:
        raise ValueError(
            "Deben existir tres ejemplos"
        )

    if len(evaluacion) == 0:
        raise ValueError(
            "No quedaron eventos para evaluar"
        )

    distribucion = Counter(
        e["etiqueta"]["nivel"]
        for e in evaluacion
    )

    protocolo = {
        "version": "fewshot_fijo_v1",
        "conjunto": "desarrollo",
        "criterio": (
            "Un ejemplo fijo por clase presente, "
            "seleccionado por longitud y event_id. "
            "Los grupos usados como demostracion "
            "se excluyen de todas las evaluaciones."
        ),
        "niveles_ejemplos": list(
            FUENTES_EJEMPLOS
        ),
        "ids_ejemplos": [
            e["event_id"] for e in ejemplos
        ],
        "grupos_reservados": [
            {
                "fuente": fuente,
                "grupo": grupo,
            }
            for fuente, grupo in sorted(
                grupos_reservados
            )
        ],
        "ids_evaluacion": [
            e["event_id"] for e in evaluacion
        ],
        "total_evaluacion": len(evaluacion),
        "distribucion_evaluacion": dict(
            distribucion
        ),
    }

    contenido = json.dumps(
        protocolo,
        ensure_ascii=False,
        indent=2,
    )

    protocolo["sha256_contenido"] = (
        hashlib.sha256(
            contenido.encode("utf-8")
        ).hexdigest()
    )

    SALIDA.parent.mkdir(
        parents=True, exist_ok=True
    )

    with SALIDA.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            protocolo,
            archivo,
            ensure_ascii=False,
            indent=2,
        )

    print("=" * 60)
    print("PROTOCOLO FEW-SHOT FIJO - A2")
    print("=" * 60)

    print("\nEJEMPLOS SELECCIONADOS")

    for ejemplo in ejemplos:
        print(
            ejemplo["etiqueta"]["nivel"],
            ejemplo["etiqueta"]["fuente"],
            ejemplo["event_id"],
        )

    print(
        "\nGrupos reservados:",
        len(grupos_reservados)
    )
    print(
        "Eventos originales dev:",
        len(desarrollo)
    )
    print(
        "Eventos para comparacion:",
        len(evaluacion)
    )

    print("\nDISTRIBUCION PARA COMPARACION")

    for nivel in ("INFO", "BAJO", "MEDIO", "ALTO"):
        print(
            f"{nivel}: {distribucion[nivel]}"
        )

    print("\nArchivo:", SALIDA)
    print("\nVALIDACION DEL PROTOCOLO: OK")


if __name__ == "__main__":
    main()

