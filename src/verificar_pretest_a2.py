
import hashlib
import json
import subprocess
from pathlib import Path

from config_llm_a2 import OPCIONES, ESQUEMA_RESPUESTA
from prompts_llm import cargar_desarrollo
from prompts_fewshot_fijo import (
    cargar_protocolo,
    construir_fewshot_fijo,
)

BASE = Path(__file__).resolve().parent.parent

CONGELADO = BASE / "docs/protocolo_test_a2.json"

DEV = (
    BASE / "data/processed/dataset/"
    "desarrollo.jsonl"
)

TEST = (
    BASE / "data/processed/dataset/"
    "prueba.jsonl"
)

ETIQUETAS = (
    BASE / "data/processed/dataset/"
    "etiquetas_multiclase.csv"
)


def sha256_bytes(datos):
    return hashlib.sha256(datos).hexdigest()


def sha256_archivo(ruta):
    return sha256_bytes(ruta.read_bytes())


def leer_jsonl(ruta):
    filas = []

    with ruta.open(encoding="utf-8") as archivo:
        for numero, linea in enumerate(archivo, 1):
            if not linea.strip():
                continue

            fila = json.loads(linea)

            if not isinstance(fila, dict):
                raise ValueError(
                    f"Fila incorrecta: {ruta}:{numero}"
                )

            filas.append(fila)

    return filas


def comprobar_git(congelado):
    commit = congelado["commit_fuente"]

    resultado = subprocess.run(
        ["git", "cat-file", "-t", commit],
        cwd=BASE,
        capture_output=True,
        text=True,
        check=True,
    )

    if resultado.stdout.strip() != "commit":
        raise ValueError("Commit fuente no encontrado")

    for nombre, hash_esperado in (
        congelado["sha256_codigo"].items()
    ):
        ruta = BASE / nombre

        if sha256_archivo(ruta) != hash_esperado:
            raise ValueError(
                "Codigo modificado: " + nombre
            )


def comprobar_dataset(congelado):
    if (
        sha256_archivo(ETIQUETAS)
        != congelado["dataset_referencia"][
            "sha256_etiquetas"
        ]
    ):
        raise ValueError(
            "Las etiquetas originales cambiaron"
        )

    desarrollo = leer_jsonl(DEV)
    prueba = leer_jsonl(TEST)

    ids_dev = [e["event_id"] for e in desarrollo]
    ids_test = [e["event_id"] for e in prueba]

    if len(ids_dev) != 158:
        raise ValueError("Dev no contiene 158 eventos")

    if len(ids_test) != 361:
        raise ValueError("Test no contiene 361 eventos")

    if len(set(ids_dev)) != len(ids_dev):
        raise ValueError("IDs duplicados en dev")

    if len(set(ids_test)) != len(ids_test):
        raise ValueError("IDs duplicados en test")

    if set(ids_dev) & set(ids_test):
        raise ValueError(
            "Filtracion: IDs compartidos dev/test"
        )

    for evento in prueba:
        if not isinstance(evento.get("texto"), str):
            raise ValueError(
                "Texto de evento invalido: "
                + evento["event_id"]
            )

        if not evento["texto"].strip():
            raise ValueError(
                "Evento vacio: " + evento["event_id"]
            )

    return prueba


def comprobar_ejemplos(congelado):
    desarrollo = cargar_desarrollo()
    protocolo, ejemplos = cargar_protocolo(
        desarrollo
    )

    ids = [e["event_id"] for e in ejemplos]

    if ids != congelado["ejemplos"]["ids"]:
        raise ValueError("Ejemplos modificados")

    for evento in ejemplos:
        identificador = evento["event_id"]

        hash_actual = sha256_bytes(
            evento["texto"].encode("utf-8")
        )

        hash_esperado = (
            congelado["ejemplos"]["sha256_textos"][
                identificador
            ]
        )

        if hash_actual != hash_esperado:
            raise ValueError(
                "Texto de ejemplo modificado: "
                + identificador
            )

    return ejemplos


def comprobar_prompts(prueba, ejemplos):
    maximo_bytes = 0
    maximo_evento = None
    hashes = set()

    for evento in prueba:
        # Solo entregar identificador y texto.
        # No pasar etiquetas ni fuente experimental.
        entrada = {
            "event_id": evento["event_id"],
            "texto": evento["texto"],
        }

        prompt = construir_fewshot_fijo(
            entrada, ejemplos
        )

        longitud = len(prompt.encode("utf-8"))

        if longitud > 12000:
            raise ValueError(
                "Prompt supera limite preventivo: "
                + evento["event_id"]
            )

        if not prompt.endswith(
            "RESPUESTA JSON:"
        ):
            raise ValueError(
                "Prompt incompleto: "
                + evento["event_id"]
            )

        hashes.add(
            sha256_bytes(prompt.encode("utf-8"))
        )

        if longitud > maximo_bytes:
            maximo_bytes = longitud
            maximo_evento = evento["event_id"]

    print(
        "Prompts únicos:",
        len(hashes)
    )
    print(
        "Eventos con prompt repetido:",
        len(prueba) - len(hashes)
    )

    return maximo_bytes, maximo_evento


def main():
    with CONGELADO.open(
        encoding="utf-8"
    ) as archivo:
        congelado = json.load(archivo)

    assert (
        congelado["estado"]
        == "CONGELADO_ANTES_DE_TEST"
    )

    assert OPCIONES == congelado["opciones"]

    assert (
        ESQUEMA_RESPUESTA
        == congelado["esquema_respuesta"]
    )

    assert (
        congelado["evaluacion_test"][
            "eventos_esperados"
        ] == 361
    )

    assert (
        congelado["evaluacion_test"][
            "corridas_por_clasificador"
        ] == 3
    )

    comprobar_git(congelado)

    prueba = comprobar_dataset(congelado)
    ejemplos = comprobar_ejemplos(congelado)

    maximo, identificador = comprobar_prompts(
        prueba, ejemplos
    )

    print("=" * 60)
    print("VERIFICACION PRETEST - TP FINAL A2")
    print("=" * 60)

    print("Codigo congelado: OK")
    print("Etiquetas sin modificar: OK")
    print("Eventos DEV: 158")
    print("Eventos TEST:", len(prueba))
    print("Solapamiento DEV/TEST: 0")
    print("Ejemplos fijos:", len(ejemplos))
    print("Hashes de ejemplos: OK")
    print("Opciones Ollama: OK")
    print("Esquema JSON: OK")

    print(
        "Mayor prompt (bytes UTF-8):",
        maximo
    )
    print("Evento correspondiente:", identificador)

    print(
        "Prompts construidos:",
        len(prueba)
    )

    print(
        "No se ejecutaron inferencias ni "
        "se consultaron etiquetas de test."
    )

    print("\nVERIFICACION PRETEST: OK")


if __name__ == "__main__":
    main()

