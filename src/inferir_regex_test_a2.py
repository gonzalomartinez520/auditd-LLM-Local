
import argparse
import hashlib
import json
import math
import resource
import statistics
import time
from pathlib import Path

from clasificador_regex_multiclase import (
    clasificar_evento,
    validar_resultado,
)

BASE = Path(__file__).resolve().parent.parent

TEST = (
    BASE / "data/processed/dataset/prueba.jsonl"
)

DEV = (
    BASE / "data/processed/dataset/desarrollo.jsonl"
)

PROTOCOLO = BASE / "docs/protocolo_test_a2.json"

SALIDAS = BASE / "results/regex_test"

ARCHIVOS_CODIGO = [
    "src/clasificador_regex.py",
    "src/clasificador_regex_multiclase.py",
]


def sha256_bytes(datos):
    return hashlib.sha256(datos).hexdigest()


def sha256_archivo(ruta):
    return sha256_bytes(ruta.read_bytes())


def cargar_eventos(ruta):
    eventos = []

    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            original = json.loads(linea)

            eventos.append({
                "event_id": original["event_id"],
                "texto": original["texto"],
            })

    return eventos


def verificar_pretest():
    with PROTOCOLO.open(encoding="utf-8") as archivo:
        protocolo = json.load(archivo)

    if protocolo["estado"] != "CONGELADO_ANTES_DE_TEST":
        raise ValueError("Protocolo no congelado")

    if (
        protocolo["evaluacion_test"]["eventos_esperados"]
        != 361
    ):
        raise ValueError("Cantidad congelada incorrecta")

    if (
        protocolo["evaluacion_test"]["corridas_por_clasificador"]
        != 3
    ):
        raise ValueError("Cantidad de corridas incorrecta")

    if (
        "regex_multiclase"
        not in protocolo["evaluacion_test"]["clasificadores"]
    ):
        raise ValueError("Regex no figura en el protocolo")

    # Comprobar que las reglas sigan congeladas.
    for nombre in ARCHIVOS_CODIGO:
        actual = sha256_archivo(BASE / nombre)

        esperado = protocolo[
            "sha256_codigo"
        ][nombre]

        if actual != esperado:
            raise ValueError(
                "Archivo de reglas modificado: " + nombre
            )

    eventos = cargar_eventos(TEST)
    desarrollo = cargar_eventos(DEV)

    ids_test = [e["event_id"] for e in eventos]
    ids_dev = [e["event_id"] for e in desarrollo]

    if len(eventos) != 361:
        raise ValueError("Test debe contener 361 eventos")

    if len(desarrollo) != 158:
        raise ValueError("Dev debe contener 158 eventos")

    if len(set(ids_test)) != 361:
        raise ValueError("IDs duplicados en test")

    if len(set(ids_dev)) != 158:
        raise ValueError("IDs duplicados en desarrollo")

    if set(ids_test) & set(ids_dev):
        raise ValueError("Solapamiento de IDs dev/test")

    for evento in eventos:
        if (
            not isinstance(evento["texto"], str)
            or not evento["texto"].strip()
        ):
            raise ValueError(
                "Texto invalido: " + evento["event_id"]
            )

    return protocolo, eventos


def percentil95(valores):
    ordenados = sorted(valores)

    indice = math.ceil(0.95 * len(ordenados)) - 1

    return ordenados[indice]


def ram_pico_python_mib():
    """
    Linux: ru_maxrss se expresa en KiB.
    Mide el pico RSS del proceso Python completo.
    """
    kb = resource.getrusage(
        resource.RUSAGE_SELF
    ).ru_maxrss

    return kb / 1024


def ejecutar(corrida, preflight=False):
    protocolo, eventos = verificar_pretest()

    nombre = f"regex_multiclase_corrida_{corrida}"

    salida = SALIDAS / f"{nombre}.jsonl"
    resumen_ruta = SALIDAS / f"{nombre}_recursos.json"

    codigo_hash = {
        nombre: sha256_archivo(BASE / nombre)
        for nombre in ARCHIVOS_CODIGO
    }

    configuracion = {
        "clasificador": "regex_multiclase",
        "corrida": corrida,
        "commit_fuente": protocolo["commit_fuente"],
        "sha256_codigo": codigo_hash,
        "eventos_esperados": 361,
    }

    hash_config = sha256_bytes(
        json.dumps(
            configuracion,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    )

    print("=" * 60)
    print("INFERENCIA REGEX TEST - A2")
    print("=" * 60)
    print("Clasificador: regex_multiclase")
    print("Corrida:", corrida)
    print("Eventos:", len(eventos))
    print("Reglas congeladas: OK")
    print("Hash config:", hash_config)

    if preflight:
        print(
            "\nPRE-FLIGHT REGEX: OK "
            "(no se realizaron clasificaciones)"
        )
        return

    if salida.exists() or resumen_ruta.exists():
        raise SystemExit(
            "Ya existen resultados para esta corrida. "
            "No se sobrescribiran."
        )

    SALIDAS.mkdir(parents=True, exist_ok=True)

    tiempos = []
    invalidos = 0
    procesados = 0

    ram_inicial = ram_pico_python_mib()
    inicio_corrida = time.perf_counter()

    with salida.open("x", encoding="utf-8") as archivo:
        for evento in eventos:
            identificador = evento["event_id"]

            inicio = time.perf_counter_ns()

            prediccion = clasificar_evento(
                evento["texto"]
            )

            tiempo_s = (
                time.perf_counter_ns() - inicio
            ) / 1_000_000_000

            valido = True
            motivo = None

            try:
                validar_resultado(prediccion)
            except (ValueError, TypeError) as error:
                valido = False
                motivo = str(error)
                invalidos += 1

            fila = {
                "event_id": identificador,
                "serial": identificador.split(":")[-1],
                "clasificador": "regex_multiclase",
                "corrida": corrida,
                "hash_config": hash_config,
                "hash_entrada": sha256_bytes(
                    evento["texto"].encode("utf-8")
                ),
                "prediccion": prediccion,
                "valido": valido,
                "motivo_invalidez": motivo,
                "tiempo_s": tiempo_s,
            }

            archivo.write(
                json.dumps(
                    fila,
                    ensure_ascii=False,
                ) + "\n"
            )

            tiempos.append(tiempo_s)
            procesados += 1

    duracion_total = (
        time.perf_counter() - inicio_corrida
    )

    ram_pico = ram_pico_python_mib()

    resumen = {
        "clasificador": "regex_multiclase",
        "corrida": corrida,
        "hash_config": hash_config,
        "eventos": procesados,
        "invalidos": invalidos,
        "tiempo_ejecucion_s": duracion_total,
        "tiempo_medio_s": statistics.mean(tiempos),
        "tiempo_p95_s": percentil95(tiempos),
        "ram_pico_rss_python_mib": ram_pico,
        "ram_pico_previo_mib": ram_inicial,
        "metodo_ram": (
            "Linux ru_maxrss: pico RSS del proceso "
            "Python completo, incluyendo interprete "
            "y clasificador. No representa memoria "
            "exclusiva de las reglas regex."
        ),
        "tokens_entrada": None,
        "tokens_salida": None,
    }

    with resumen_ruta.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            resumen,
            archivo,
            ensure_ascii=False,
            indent=2,
        )

    print("\n" + "=" * 60)
    print("CORRIDA REGEX FINALIZADA")
    print("=" * 60)

    print("Corrida:", corrida)
    print("Eventos:", procesados)
    print("Invalidos:", invalidos)
    print(
        "Tiempo medio:",
        f'{resumen["tiempo_medio_s"]:.8f} s'
    )
    print(
        "Tiempo p95:",
        f'{resumen["tiempo_p95_s"]:.8f} s'
    )
    print(
        "RAM pico Python:",
        f"{ram_pico:.2f} MiB"
    )
    print("Archivo:", salida)
    print("Recursos:", resumen_ruta)

    print("\nINFERENCIA REGEX TEST: OK")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--corrida",
        type=int,
        required=True,
        choices=[1, 2, 3],
    )

    parser.add_argument(
        "--preflight",
        action="store_true",
    )

    args = parser.parse_args()

    ejecutar(
        args.corrida,
        preflight=args.preflight,
    )


if __name__ == "__main__":
    main()

