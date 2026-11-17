
import csv
import json
import time
from collections import Counter
from pathlib import Path

from clasificador_regex_multiclase import (
    NIVELES,
    clasificar_evento,
)

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/processed/dataset"
RESULTS = BASE / "results"

DEV = DATA / "desarrollo.jsonl"
ETIQUETAS = DATA / "etiquetas_multiclase.csv"

SALIDA = RESULTS / "regex_multiclase_dev.jsonl"
RESUMEN = RESULTS / "regex_multiclase_dev_resumen.json"


def calcular_f1(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0
    )

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main():
    if SALIDA.exists() or RESUMEN.exists():
        raise SystemExit(
            "ERROR: ya existen resultados. "
            "No se sobrescribiran."
        )

    with ETIQUETAS.open(
        newline="", encoding="utf-8"
    ) as archivo:
        etiquetas = {
            fila["event_id"]: fila
            for fila in csv.DictReader(archivo)
        }

    eventos = []

    with DEV.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if linea.strip():
                eventos.append(json.loads(linea))

    if len(eventos) != 158:
        raise ValueError("Dev debe contener 158 eventos")

    resultados = []
    tiempos = []

    for evento in eventos:
        identificador = evento["event_id"]
        referencia = etiquetas[identificador]

        inicio = time.perf_counter_ns()

        prediccion = clasificar_evento(evento["texto"])

        duracion = (
            time.perf_counter_ns() - inicio
        ) / 1_000_000_000

        tiempos.append(duracion)

        resultados.append({
            "event_id": identificador,
            "serial": referencia["serial"],
            "fuente": referencia["fuente"],
            "real_amenaza": int(referencia["amenaza"]),
            "real_nivel": referencia["nivel"],
            "real_tipo": referencia["tipo"],
            "prediccion": prediccion,
            "tiempo_s": duracion,
            "valido": True,
        })

    # Matriz: filas reales, columnas predichas.
    matriz = {
        nivel: {p: 0 for p in NIVELES}
        for nivel in NIVELES
    }

    for fila in resultados:
        matriz[fila["real_nivel"]][
            fila["prediccion"]["nivel"]
        ] += 1

    # Evaluacion binaria.
    tp = tn = fp = fn = 0

    for fila in resultados:
        real = fila["real_amenaza"]
        predicho = int(
            fila["prediccion"]["amenaza"]
        )

        if real == 1 and predicho == 1:
            tp += 1
        elif real == 0 and predicho == 0:
            tn += 1
        elif real == 0 and predicho == 1:
            fp += 1
        else:
            fn += 1

    binarias = calcular_f1(tp, fp, fn)

    # Metricas individuales por nivel.
    por_nivel = {}

    for nivel in NIVELES:
        verdaderos = matriz[nivel][nivel]

        falsos_positivos = sum(
            matriz[otro][nivel]
            for otro in NIVELES
            if otro != nivel
        )

        falsos_negativos = sum(
            matriz[nivel][otro]
            for otro in NIVELES
            if otro != nivel
        )

        cantidad_real = sum(matriz[nivel].values())

        metricas = calcular_f1(
            verdaderos,
            falsos_positivos,
            falsos_negativos,
        )

        if cantidad_real == 0:
            metricas["recall"] = None

        por_nivel[nivel] = {
            "soporte": cantidad_real,
            **metricas,
        }

    # Macro F1 para las clases presentes.
    niveles_presentes = [
        nivel for nivel in NIVELES
        if por_nivel[nivel]["soporte"] > 0
    ]

    macro_f1_presentes = sum(
        por_nivel[nivel]["f1"]
        for nivel in niveles_presentes
    ) / len(niveles_presentes)

    por_fuente = {}

    for fuente in sorted({
        fila["fuente"] for fila in resultados
    }):
        subconjunto = [
            fila for fila in resultados
            if fila["fuente"] == fuente
        ]

        por_fuente[fuente] = {
            "eventos": len(subconjunto),
            "niveles_predichos": dict(Counter(
                fila["prediccion"]["nivel"]
                for fila in subconjunto
            )),
            "tipos_correctos": sum(
                fila["real_tipo"]
                == fila["prediccion"]["tipo"]
                for fila in subconjunto
            ),
        }

    resumen = {
        "clasificador": "regex_multiclase",
        "conjunto": "desarrollo",
        "eventos": len(resultados),
        "matriz_niveles": matriz,
        "metricas_binarias": {
            "TP": tp,
            "TN": tn,
            "FP": fp,
            "FN": fn,
            **binarias,
        },
        "metricas_por_nivel": por_nivel,
        "macro_f1_clases_presentes": macro_f1_presentes,
        "tiempo_medio_s": sum(tiempos) / len(tiempos),
        "respuestas_invalidas": 0,
        "por_fuente": por_fuente,
    }

    RESULTS.mkdir(parents=True, exist_ok=True)

    with SALIDA.open(
        "x", encoding="utf-8"
    ) as archivo:
        for fila in resultados:
            archivo.write(
                json.dumps(
                    fila, ensure_ascii=False
                ) + "\n"
            )

    with RESUMEN.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            resumen,
            archivo,
            ensure_ascii=False,
            indent=2,
        )

    print("=" * 60)
    print("REGEX MULTICLASE - DESARROLLO A2")
    print("=" * 60)

    print("Eventos:", len(resultados))

    print("\nMETRICAS BINARIAS")
    for campo in ("TP", "TN", "FP", "FN"):
        print(f"{campo}: {resumen['metricas_binarias'][campo]}")

    for campo in ("precision", "recall", "f1"):
        print(
            f"{campo}: "
            f"{binarias[campo]:.4f}"
        )

    print("\nMATRIZ DE CONFUSION DE CUATRO NIVELES")
    print("Real \\ Predicho")
    print(
        f"{'':8}"
        + "".join(f"{n:>8}" for n in NIVELES)
    )

    for nivel in NIVELES:
        print(
            f"{nivel:8}"
            + "".join(
                f"{matriz[nivel][p]:>8}"
                for p in NIVELES
            )
        )

    print("\nF1 POR NIVEL")
    for nivel in NIVELES:
        info = por_nivel[nivel]
        print(
            f"{nivel}: "
            f"soporte={info['soporte']}, "
            f"F1={info['f1']:.4f}"
        )

    print(
        "\nMacro F1 (clases presentes):",
        f"{macro_f1_presentes:.4f}"
    )

    print("\nPOR ESCENARIO")
    for fuente, datos in por_fuente.items():
        print(
            fuente,
            datos["niveles_predichos"],
            "tipos correctos:",
            f"{datos['tipos_correctos']}/{datos['eventos']}"
        )

    print("\nVALIDACION REGEX MULTICLASE: OK")


if __name__ == "__main__":
    main()

