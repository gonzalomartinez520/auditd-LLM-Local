
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/processed/dataset"
LLM = BASE / "results/llm_test"
REGEX = BASE / "results/regex_test"
SALIDA = BASE / "results/analisis_final"

TEST = DATA / "prueba.jsonl"
DEV = DATA / "desarrollo.jsonl"
ETIQUETAS = DATA / "etiquetas_multiclase.csv"
PROTOCOLO = BASE / "docs/protocolo_test_a2.json"

NIVELES = ["INFO", "BAJO", "MEDIO", "ALTO"]
MODELOS = ["regex_multiclase", "qwen3:0.6b", "gemma3:1b"]


def sha256(datos):
    return hashlib.sha256(datos).hexdigest()


def leer_json(ruta):
    with ruta.open(encoding="utf-8") as f:
        return json.load(f)


def leer_jsonl(ruta):
    filas = {}
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            fila = json.loads(linea)
            eid = fila["event_id"]
            if eid in filas:
                raise ValueError(f"ID duplicado: {ruta} {eid}")
            filas[eid] = fila
    return filas


def cargar_referencias():
    protocolo = leer_json(PROTOCOLO)

    if sha256(ETIQUETAS.read_bytes()) != (
        protocolo["dataset_referencia"]["sha256_etiquetas"]
    ):
        raise ValueError("Las etiquetas cambiaron")

    test = leer_jsonl(TEST)
    dev = leer_jsonl(DEV)

    if len(test) != 361 or len(dev) != 158:
        raise ValueError("Cantidad de eventos incorrecta")

    if set(test) & set(dev):
        raise ValueError("DEV y TEST comparten IDs")

    with ETIQUETAS.open(newline="", encoding="utf-8") as f:
        etiquetas = {
            fila["event_id"]: fila
            for fila in csv.DictReader(f)
        }

    if not set(test).issubset(etiquetas):
        raise ValueError("Faltan etiquetas de test")

    return test, dev, etiquetas


def ruta_predicciones(modelo, corrida):
    if modelo == "regex_multiclase":
        return REGEX / (
            f"regex_multiclase_corrida_{corrida}.jsonl"
        )

    nombre = modelo.replace(":", "_")
    return LLM / f"{nombre}_corrida_{corrida}.jsonl"


def cargar_corridas(modelo, test):
    corridas = {}
    ids = set(test)

    for numero in (1, 2, 3):
        ruta = ruta_predicciones(modelo, numero)
        filas = leer_jsonl(ruta)

        if set(filas) != ids:
            raise ValueError(
                f"IDs incompletos: {modelo}/{numero}"
            )

        hashes_config = {
            f["hash_config"] for f in filas.values()
        }
        if len(hashes_config) != 1:
            raise ValueError("Hash config inconsistente")

        for eid, fila in filas.items():
            if fila["corrida"] != numero:
                raise ValueError("Corrida incorrecta")

            if fila["serial"] != eid.split(":")[-1]:
                raise ValueError("Serial incorrecto")

            if modelo == "regex_multiclase":
                if fila["clasificador"] != modelo:
                    raise ValueError("Clasificador incorrecto")

                esperado = sha256(
                    test[eid]["texto"].encode("utf-8")
                )
                if fila["hash_entrada"] != esperado:
                    raise ValueError("Entrada regex cambiada")
            elif fila["modelo"] != modelo:
                raise ValueError("Modelo incorrecto")

            if not fila["valido"]:
                continue

            p = fila["prediccion"]
            if (
                not isinstance(p, dict)
                or set(p) != {
                    "amenaza", "nivel",
                    "tipo", "explicacion"
                }
                or type(p["amenaza"]) is not bool
                or p["nivel"] not in NIVELES
                or p["amenaza"] != (p["nivel"] != "INFO")
                or not isinstance(p["tipo"], str)
                or not isinstance(p["explicacion"], str)
                or not p["explicacion"].strip()
            ):
                raise ValueError(
                    f"Prediccion incoherente: {modelo}/{eid}"
                )

        corridas[numero] = filas

    # Las configuraciones y hashes completos de los LLM
    # fueron comprobados previamente por la auditoria.
    if modelo != "regex_multiclase":
        for eid in ids:
            hashes = {
                corridas[n][eid]["hash_prompt"]
                for n in (1, 2, 3)
            }
            if len(hashes) != 1:
                raise ValueError(
                    f"Prompt diferente entre corridas: {eid}"
                )

    return corridas


def f1(tp, fp, fn):
    d = 2 * tp + fp + fn
    return (2 * tp / d) if d else 0.0


def p95(valores):
    orden = sorted(valores)
    return orden[math.ceil(0.95 * len(orden)) - 1]


def metricas(filas):
    tp = tn = fp = fn = invalidos = 0
    matriz = {
        real: {
            pred: 0 for pred in NIVELES + ["INVALIDA"]
        }
        for real in NIVELES
    }

    tiempos = []
    errores = []

    for fila in filas:
        real = fila["real_amenaza"]
        nivel_real = fila["real_nivel"]
        tiempos.append(fila["tiempo_s"])

        if not fila["valido"]:
            invalidos += 1
            nivel_pred = "INVALIDA"
            pred_amenaza = None
            if real:
                fn += 1
            else:
                fp += 1
        else:
            pred = fila["prediccion"]
            nivel_pred = pred["nivel"]
            pred_amenaza = int(pred["amenaza"])

            if real == 1 and pred_amenaza == 1:
                tp += 1
            elif real == 0 and pred_amenaza == 0:
                tn += 1
            elif real == 0:
                fp += 1
            else:
                fn += 1

        matriz[nivel_real][nivel_pred] += 1

        if pred_amenaza is None:
            error = "RESPUESTA_INVALIDA"
        elif real == 0 and pred_amenaza == 1:
            error = "FP"
        elif real == 1 and pred_amenaza == 0:
            error = "FN"
        else:
            error = None

        if error:
            errores.append({
                "event_id": fila["event_id"],
                "fuente": fila["fuente"],
                "error": error,
                "nivel_real": nivel_real,
                "nivel_predicho": nivel_pred,
                "tipo_real": fila["real_tipo"],
                "tipo_predicho": (
                    fila["prediccion"].get("tipo")
                    if fila["valido"] else None
                ),
            })

    por_nivel = {}
    for nivel in NIVELES:
        soporte = sum(matriz[nivel].values())
        aciertos = matriz[nivel][nivel]
        fp_n = sum(
            matriz[otro][nivel]
            for otro in NIVELES if otro != nivel
        )
        fn_n = soporte - aciertos

        por_nivel[nivel] = {
            "soporte": soporte,
            "precision": (
                aciertos / (aciertos + fp_n)
                if aciertos + fp_n else 0.0
            ),
            "recall": (
                aciertos / soporte if soporte else None
            ),
            "f1": f1(aciertos, fp_n, fn_n),
        }

    presentes = [
        n for n in NIVELES
        if por_nivel[n]["soporte"] > 0
    ]

    return {
        "eventos": len(filas),
        "TP": tp, "TN": tn,
        "FP_penalizado": fp,
        "FN_penalizado": fn,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "f1_binario": f1(tp, fp, fn),
        "invalidos": invalidos,
        "matriz_niveles": matriz,
        "por_nivel": por_nivel,
        "macro_f1_clases_presentes": statistics.mean(
            por_nivel[n]["f1"] for n in presentes
        ),
        "tiempo_medio_s": statistics.mean(tiempos),
        "tiempo_p95_s": p95(tiempos),
        "errores": errores,
    }


def main():
    if SALIDA.exists() and any(SALIDA.iterdir()):
        raise SystemExit(
            "Ya existen resultados finales. "
            "No se sobrescribiran."
        )

    test, dev, etiquetas = cargar_referencias()

    textos_dev = {
        sha256(e["texto"].encode("utf-8"))
        for e in dev.values()
    }

    reporte = {
        "eventos_test": 361,
        "corridas_por_clasificador": 3,
        "resultados": {},
    }
    resumen_csv = []
    errores_csv = []

    for modelo in MODELOS:
        corridas = cargar_corridas(modelo, test)
        resultados = {}

        for numero in (1, 2, 3):
            filas = []

            for eid, evento in test.items():
                referencia = etiquetas[eid]
                original = corridas[numero][eid]

                filas.append({
                    **original,
                    "real_amenaza":
                        int(referencia["amenaza"]),
                    "real_nivel": referencia["nivel"],
                    "real_tipo": referencia["tipo"],
                    "fuente": referencia["fuente"],
                })

            total = metricas(filas)

            por_fuente = {}
            for fuente in sorted({
                fila["fuente"] for fila in filas
            }):
                subset = [
                    fila for fila in filas
                    if fila["fuente"] == fuente
                ]
                m = metricas(subset)

                por_fuente[fuente] = {
                    "eventos": m["eventos"],
                    "TP": m["TP"],
                    "TN": m["TN"],
                    "FP": m["FP_penalizado"],
                    "FN": m["FN_penalizado"],
                    "f1": m["f1_binario"],
                }

            conocidos = []
            nuevos = []

            for fila in filas:
                huella = sha256(
                    test[fila["event_id"]]["texto"]
                    .encode("utf-8")
                )
                if huella in textos_dev:
                    conocidos.append(fila)
                else:
                    nuevos.append(fila)

            total["por_fuente"] = por_fuente
            total["texto_conocido"] = {
                "eventos": len(conocidos),
                "metricas": {
                    k: v for k, v
                    in metricas(conocidos).items()
                    if k in (
                        "TP", "TN",
                        "FP_penalizado",
                        "FN_penalizado",
                        "f1_binario"
                    )
                },
            }
            total["texto_nuevo"] = {
                "eventos": len(nuevos),
                "metricas": {
                    k: v for k, v
                    in metricas(nuevos).items()
                    if k in (
                        "TP", "TN",
                        "FP_penalizado",
                        "FN_penalizado",
                        "f1_binario"
                    )
                },
            }

            for error in total["errores"]:
                errores_csv.append({
                    "modelo": modelo,
                    "corrida": numero,
                    **error,
                })

            # Guardamos todos los errores en un CSV;
            # las primeras 20 muestras se analizaran
            # posteriormente sin alterar las etiquetas.
            del total["errores"]
            resultados[str(numero)] = total

            resumen_csv.append({
                "modelo": modelo,
                "corrida": numero,
                **{
                    k: total[k]
                    for k in (
                        "TP", "TN",
                        "FP_penalizado",
                        "FN_penalizado",
                        "precision", "recall",
                        "f1_binario", "invalidos",
                        "macro_f1_clases_presentes",
                        "tiempo_medio_s",
                        "tiempo_p95_s",
                    )
                },
            })

        f1s = [
            resultados[str(n)]["f1_binario"]
            for n in (1, 2, 3)
        ]

        reporte["resultados"][modelo] = {
            "corridas": resultados,
            "f1_media": statistics.mean(f1s),
            "f1_desviacion": statistics.pstdev(f1s),
        }

    SALIDA.mkdir(parents=True, exist_ok=True)

    with (SALIDA / "resultados_test.json").open(
        "x", encoding="utf-8"
    ) as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    with (SALIDA / "resumen_corridas.csv").open(
        "x", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=list(resumen_csv[0])
        )
        writer.writeheader()
        writer.writerows(resumen_csv)

    with (SALIDA / "errores_test.csv").open(
        "x", newline="", encoding="utf-8"
    ) as f:
        campos = [
            "modelo", "corrida", "event_id",
            "fuente", "error", "nivel_real",
            "nivel_predicho", "tipo_real",
            "tipo_predicho",
        ]
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(errores_csv)

    print("=" * 65)
    print("RESULTADOS FINALES - TP A2")
    print("=" * 65)

    for fila in resumen_csv:
        print(
            f"{fila['modelo']:<19} "
            f"C{fila['corrida']} "
            f"TP={fila['TP']:>3} "
            f"TN={fila['TN']:>3} "
            f"FP={fila['FP_penalizado']:>3} "
            f"FN={fila['FN_penalizado']:>3} "
            f"F1={fila['f1_binario']:.4f} "
            f"MacroF1={fila['macro_f1_clases_presentes']:.4f}"
        )

    print("\nPROMEDIO DE F1 ENTRE CORRIDAS")
    for modelo, datos in reporte["resultados"].items():
        print(
            f"{modelo}: {datos['f1_media']:.4f} "
            f"(desviacion={datos['f1_desviacion']:.4f})"
        )

    print("\nArchivos:", SALIDA)
    print("ANALISIS TEST: OK")


if __name__ == "__main__":
    main()

