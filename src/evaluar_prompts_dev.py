
import argparse
import hashlib
import json
import math
import statistics
import time
import urllib.request
from collections import Counter
from pathlib import Path

from config_llm_a2 import (
    URL_OLLAMA, MODELOS, ESTRATEGIAS,
    OPCIONES, ESQUEMA_RESPUESTA,
    validar_prediccion,
)
from prompts_llm import cargar_desarrollo, construir_prompt

BASE = Path(__file__).resolve().parent.parent
RESULTS = BASE / "results/llm_dev"
NIVELES = ("INFO", "BAJO", "MEDIO", "ALTO")
TOTAL = 158


def hash_objeto(objeto):
    contenido = json.dumps(
        objeto, sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(
        contenido.encode("utf-8")
    ).hexdigest()


def percentil95(valores):
    ordenados = sorted(valores)
    indice = math.ceil(0.95 * len(ordenados)) - 1
    return ordenados[indice]


def consultar(modelo, prompt):
    solicitud = {
        "model": modelo,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": ESQUEMA_RESPUESTA,
        "options": OPCIONES,
        "keep_alive": "5m",
    }

    peticion = urllib.request.Request(
        URL_OLLAMA,
        data=json.dumps(solicitud).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    inicio = time.perf_counter()

    with urllib.request.urlopen(
        peticion, timeout=600
    ) as respuesta:
        datos = json.load(respuesta)

    segundos = time.perf_counter() - inicio

    respuesta_original = datos.get("response", "")

    try:
        prediccion = json.loads(respuesta_original)
        valido = validar_prediccion(prediccion)
    except (json.JSONDecodeError, TypeError, ValueError):
        prediccion = None
        valido = False

    tokens_entrada = datos.get("prompt_eval_count")
    tokens_salida = datos.get("eval_count")

    limite_entrada = (
        OPCIONES["num_ctx"] - OPCIONES["num_predict"]
    )

    contexto_revisar = (
        not isinstance(tokens_entrada, int)
        or tokens_entrada >= limite_entrada
        or not datos.get("done", False)
    )

    return {
        "prediccion": prediccion,
        "respuesta_original": respuesta_original,
        "valido": valido,
        "tiempo_s": round(segundos, 6),
        "prompt_eval_count": tokens_entrada,
        "eval_count": tokens_salida,
        "total_duration_s": (
            datos.get("total_duration", 0) / 1e9
        ),
        "load_duration_s": (
            datos.get("load_duration", 0) / 1e9
        ),
        "prompt_eval_duration_s": (
            datos.get("prompt_eval_duration", 0) / 1e9
        ),
        "eval_duration_s": (
            datos.get("eval_duration", 0) / 1e9
        ),
        "contexto_revisar": contexto_revisar,
    }


def leer_previos(ruta):
    anteriores = {}

    if not ruta.exists():
        return anteriores

    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            fila = json.loads(linea)
            identificador = fila["event_id"]

            if identificador in anteriores:
                raise ValueError(
                    f"Prediccion duplicada: {identificador}"
                )

            anteriores[identificador] = fila

    return anteriores


def preparar_trabajos(estrategia, desarrollo):
    trabajos = {}

    for evento in desarrollo:
        construido = construir_prompt(
            estrategia, evento, desarrollo
        )

        prompt = construido["prompt"]

        # Limite operativo preventivo, no prueba
        # de ausencia de truncamiento.
        if len(prompt.encode("utf-8")) > 12000:
            raise ValueError(
                "Prompt demasiado grande: "
                + evento["event_id"]
            )

        trabajos[evento["event_id"]] = {
            "prompt": prompt,
            "hash_prompt": hashlib.sha256(
                prompt.encode("utf-8")
            ).hexdigest(),
            "ids_ejemplos": construido["ids_ejemplos"],
        }

    return trabajos


def calcular_metricas(filas):
    # Las respuestas invalidas cuentan como error:
    # positivo real invalido => FN penalizado;
    # negativo real invalido => FP penalizado.
    tp = tn = fp = fn = 0
    invalidos = 0

    matriz = {
        nivel: {
            predicho: 0
            for predicho in (*NIVELES, "INVALIDA")
        }
        for nivel in NIVELES
    }

    for fila in filas:
        real = fila["real_amenaza"]
        nivel_real = fila["real_nivel"]
        pred = fila["prediccion"]
        valido = fila["valido"]

        if not valido:
            invalidos += 1
            matriz[nivel_real]["INVALIDA"] += 1

            if real == 1:
                fn += 1
            else:
                fp += 1
            continue

        matriz[nivel_real][pred["nivel"]] += 1

        amenaza_predicha = int(pred["amenaza"])

        if real == 1 and amenaza_predicha == 1:
            tp += 1
        elif real == 0 and amenaza_predicha == 0:
            tn += 1
        elif real == 0:
            fp += 1
        else:
            fn += 1

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0
    )

    tiempos = [fila["tiempo_s"] for fila in filas]

    return {
        "total": len(filas),
        "TP": tp,
        "TN": tn,
        "FP_penalizado": fp,
        "FN_penalizado": fn,
        "invalidos": invalidos,
        "tasa_invalidos": invalidos / len(filas),
        "precision_penalizada": precision,
        "recall_penalizado": recall,
        "f1_penalizado": f1,
        "accuracy_penalizada": (
            tp + tn
        ) / len(filas),
        "tiempo_medio_s": statistics.mean(tiempos),
        "tiempo_p95_s": percentil95(tiempos),
        "matriz_niveles": matriz,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--modelo", required=True,
        choices=MODELOS,
    )
    parser.add_argument(
        "--prompt", required=True,
        choices=ESTRATEGIAS,
    )

    args = parser.parse_args()

    modelo = args.modelo
    estrategia = args.prompt

    nombre_modelo = modelo.replace(":", "_")

    SALIDA = RESULTS / (
        f"{nombre_modelo}_{estrategia}.jsonl"
    )
    RESUMEN = RESULTS / (
        f"{nombre_modelo}_{estrategia}_resumen.json"
    )

    desarrollo = cargar_desarrollo()
    trabajos = preparar_trabajos(
        estrategia, desarrollo
    )

    configuracion = {
        "modelo": modelo,
        "estrategia": estrategia,
        "opciones": OPCIONES,
        "formato": ESQUEMA_RESPUESTA,
    }
    hash_config = hash_objeto(configuracion)

    RESULTS.mkdir(parents=True, exist_ok=True)

    if RESUMEN.exists():
        raise SystemExit(
            "La evaluacion ya tiene resumen final: "
            + str(RESUMEN)
        )

    previos = leer_previos(SALIDA)

    ids_dev = {
        evento["event_id"] for evento in desarrollo
    }

    if not set(previos).issubset(ids_dev):
        raise ValueError(
            "Resultados previos contienen IDs ajenos a dev"
        )

    # Verificar que una reanudacion mantenga
    # exactamente la configuracion y los prompts.
    for identificador, fila in previos.items():
        trabajo = trabajos[identificador]

        if (
            fila["hash_config"] != hash_config
            or fila["hash_prompt"] != trabajo["hash_prompt"]
        ):
            raise ValueError(
                "Configuracion o prompt cambiado: "
                + identificador
            )

    print("=" * 60)
    print("EVALUACION LLM - DESARROLLO A2")
    print("=" * 60)
    print("Modelo:", modelo)
    print("Estrategia:", estrategia)
    print("Eventos:", TOTAL)
    print("Ya procesados:", len(previos))

    with SALIDA.open("a", encoding="utf-8") as archivo:
        for evento in desarrollo:
            identificador = evento["event_id"]

            if identificador in previos:
                continue

            trabajo = trabajos[identificador]
            referencia = evento["etiqueta"]

            try:
                respuesta = consultar(
                    modelo, trabajo["prompt"]
                )
            except Exception as error:
                print(
                    f"\nError tecnico en {identificador}: "
                    f"{error}"
                )
                print(
                    "Reejecuta el mismo comando "
                    "para reanudar."
                )
                raise SystemExit(1)

            fila = {
                "event_id": identificador,
                "serial": referencia["serial"],
                "modelo": modelo,
                "estrategia": estrategia,
                "fuente": referencia["fuente"],
                "real_amenaza": int(
                    referencia["amenaza"]
                ),
                "real_nivel": referencia["nivel"],
                "real_tipo": referencia["tipo"],
                "ids_ejemplos": trabajo["ids_ejemplos"],
                "hash_prompt": trabajo["hash_prompt"],
                "hash_config": hash_config,
                **respuesta,
            }

            archivo.write(
                json.dumps(
                    fila, ensure_ascii=False
                ) + "\n"
            )
            archivo.flush()

            previos[identificador] = fila

            cantidad = len(previos)
            if cantidad % 10 == 0 or cantidad == TOTAL:
                print(
                    f"Procesados: {cantidad}/{TOTAL}",
                    flush=True,
                )

            if respuesta["contexto_revisar"]:
                print(
                    "\nATENCION: revisar contexto en "
                    + identificador
                )
                print(
                    "Se conservan los resultados "
                    "y se detiene la evaluacion."
                )
                raise SystemExit(2)

    if len(previos) != TOTAL:
        raise ValueError(
            f"Evaluacion incompleta: {len(previos)}/{TOTAL}"
        )

    filas = [
        previos[e["event_id"]]
        for e in desarrollo
    ]

    metricas = calcular_metricas(filas)

    por_fuente = {}

    for fuente in sorted({
        fila["fuente"] for fila in filas
    }):
        subconjunto = [
            fila for fila in filas
            if fila["fuente"] == fuente
        ]

        por_fuente[fuente] = {
            "eventos": len(subconjunto),
            "predicciones": dict(Counter(
                (
                    fila["prediccion"]["nivel"]
                    if fila["valido"]
                    else "INVALIDA"
                )
                for fila in subconjunto
            )),
            "f1_binario_penalizado": (
                calcular_metricas(subconjunto)[
                    "f1_penalizado"
                ]
            ),
        }

    resumen = {
        "configuracion": configuracion,
        "hash_config": hash_config,
        "metricas": metricas,
        "por_fuente": por_fuente,
        "advertencia": (
            "Las respuestas invalidas se penalizan "
            "como errores. FP/FN incluyen penalizacion "
            "y no equivalen exclusivamente a "
            "predicciones de la clase contraria."
        ),
    }

    with RESUMEN.open("x", encoding="utf-8") as archivo:
        json.dump(
            resumen, archivo,
            indent=2, ensure_ascii=False
        )

    print("\n" + "=" * 60)
    print("RESULTADOS DESARROLLO")
    print("=" * 60)
    print("TP:", metricas["TP"])
    print("TN:", metricas["TN"])
    print("FP penalizados:", metricas["FP_penalizado"])
    print("FN penalizados:", metricas["FN_penalizado"])
    print("Invalidos:", metricas["invalidos"])
    print(
        "F1 penalizado:",
        f'{metricas["f1_penalizado"]:.4f}'
    )
    print(
        "Tiempo medio:",
        f'{metricas["tiempo_medio_s"]:.4f} s'
    )
    print(
        "Tiempo p95:",
        f'{metricas["tiempo_p95_s"]:.4f} s'
    )

    print("\nPOR ESCENARIO")
    for fuente, datos in por_fuente.items():
        print(fuente, datos["predicciones"])

    print("\nEVALUACION DEV: OK")


if __name__ == "__main__":
    main()

