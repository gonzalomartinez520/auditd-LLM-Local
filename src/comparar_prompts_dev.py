
import csv
import json
import math
import statistics
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CARPETA = BASE / "results/llm_dev"

PROTOCOLO = CARPETA / "protocolo_fewshot_fijo.json"
ETIQUETAS = (
    BASE / "data/processed/dataset/"
    "etiquetas_multiclase.csv"
)

SALIDA = CARPETA / "comparacion_prompts_dev.json"
SALIDA_CSV = CARPETA / "comparacion_prompts_dev.csv"

MODELOS = ["qwen3:0.6b", "gemma3:1b"]
ESTRATEGIAS = [
    "zero_shot",
    "few_shot_fijo",
    "chain_of_thought",
]
NIVELES = ["INFO", "BAJO", "MEDIO", "ALTO"]


def cargar_json(ruta):
    with ruta.open(encoding="utf-8") as archivo:
        return json.load(archivo)


def cargar_jsonl(ruta):
    filas = {}

    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            fila = json.loads(linea)
            identificador = fila["event_id"]

            if identificador in filas:
                raise ValueError(
                    f"Duplicado en {ruta}: {identificador}"
                )

            filas[identificador] = fila

    return filas


def cargar_etiquetas():
    with ETIQUETAS.open(
        newline="", encoding="utf-8"
    ) as archivo:
        return {
            fila["event_id"]: fila
            for fila in csv.DictReader(archivo)
        }


def calcular_f1(tp, fp, fn):
    denominador = 2 * tp + fp + fn

    return (
        2 * tp / denominador
        if denominador else 0.0
    )


def percentil95(valores):
    valores = sorted(valores)

    indice = math.ceil(
        0.95 * len(valores)
    ) - 1

    return valores[indice]


def evaluar(filas, etiquetas):
    tp = tn = fp = fn = invalidos = 0

    matriz = {
        real: {
            pred: 0
            for pred in NIVELES + ["INVALIDA"]
        }
        for real in NIVELES
    }

    tiempos = []

    for fila in filas:
        identificador = fila["event_id"]
        referencia = etiquetas[identificador]

        real_amenaza = int(referencia["amenaza"])
        real_nivel = referencia["nivel"]

        if (
            fila["real_amenaza"] != real_amenaza
            or fila["real_nivel"] != real_nivel
        ):
            raise ValueError(
                "Etiqueta inconsistente: "
                + identificador
            )

        tiempos.append(fila["tiempo_s"])

        if not fila["valido"]:
            invalidos += 1
            matriz[real_nivel]["INVALIDA"] += 1

            # Penalizacion definida previamente.
            if real_amenaza:
                fn += 1
            else:
                fp += 1

            continue

        prediccion = fila["prediccion"]

        if (
            not isinstance(prediccion, dict)
            or prediccion.get("nivel") not in NIVELES
            or type(prediccion.get("amenaza")) is not bool
            or prediccion["amenaza"] != (
                prediccion["nivel"] != "INFO"
            )
        ):
            raise ValueError(
                "Prediccion marcada valida "
                "pero inconsistente: " + identificador
            )

        nivel_predicho = prediccion["nivel"]
        amenaza_predicha = int(
            prediccion["amenaza"]
        )

        matriz[real_nivel][nivel_predicho] += 1

        if real_amenaza == 1 and amenaza_predicha == 1:
            tp += 1
        elif real_amenaza == 0 and amenaza_predicha == 0:
            tn += 1
        elif real_amenaza == 0:
            fp += 1
        else:
            fn += 1

    precision = (
        tp / (tp + fp)
        if tp + fp else 0
    )
    recall = (
        tp / (tp + fn)
        if tp + fn else 0
    )

    f1_por_nivel = {}

    for nivel in NIVELES:
        soporte = sum(matriz[nivel].values())

        tp_nivel = matriz[nivel][nivel]

        fp_nivel = sum(
            matriz[otro][nivel]
            for otro in NIVELES
            if otro != nivel
        )

        fn_nivel = (
            soporte - tp_nivel
        )

        f1_por_nivel[nivel] = {
            "soporte": soporte,
            "f1": calcular_f1(
                tp_nivel,
                fp_nivel,
                fn_nivel,
            ),
        }

    presentes = [
        nivel for nivel in NIVELES
        if f1_por_nivel[nivel]["soporte"] > 0
    ]

    macro_f1 = statistics.mean(
        f1_por_nivel[nivel]["f1"]
        for nivel in presentes
    )

    return {
        "total": len(filas),
        "TP": tp,
        "TN": tn,
        "FP_penalizado": fp,
        "FN_penalizado": fn,
        "precision": precision,
        "recall": recall,
        "f1_binario": calcular_f1(tp, fp, fn),
        "f1_macro_presentes": macro_f1,
        "invalidos": invalidos,
        "tasa_invalidos": invalidos / len(filas),
        "tiempo_medio_s": statistics.mean(tiempos),
        "tiempo_p95_s": percentil95(tiempos),
        "f1_por_nivel": f1_por_nivel,
        "matriz_niveles": matriz,
    }


def ruta_resultados(modelo, estrategia):
    nombre = modelo.replace(":", "_")

    if estrategia == "few_shot_fijo":
        sufijo = "few_shot_fijo"
        cantidad_esperada = 148
    else:
        sufijo = estrategia
        cantidad_esperada = 158

    return (
        CARPETA / f"{nombre}_{sufijo}.jsonl",
        cantidad_esperada,
    )


def main():
    if SALIDA.exists() or SALIDA_CSV.exists():
        raise SystemExit(
            "ERROR: ya existe una comparacion. "
            "No se sobrescribira."
        )

    protocolo = cargar_json(PROTOCOLO)
    etiquetas = cargar_etiquetas()

    ids = protocolo["ids_evaluacion"]
    conjunto = set(ids)

    if len(ids) != 148 or len(conjunto) != 148:
        raise ValueError(
            "El protocolo no contiene 148 IDs unicos"
        )

    resultados = []
    detalle = {}

    for modelo in MODELOS:
        for estrategia in ESTRATEGIAS:
            ruta, total_archivo = ruta_resultados(
                modelo, estrategia
            )

            predicciones = cargar_jsonl(ruta)

            if len(predicciones) != total_archivo:
                raise ValueError(
                    f"Cantidad incorrecta en {ruta}"
                )

            if not conjunto.issubset(predicciones):
                raise ValueError(
                    f"Faltan eventos en {ruta}"
                )

            if estrategia == "few_shot_fijo":
                if set(predicciones) != conjunto:
                    raise ValueError(
                        "Few-shot contiene IDs ajenos "
                        "a la comparacion"
                    )

            filas = [
                predicciones[identificador]
                for identificador in ids
            ]

            for fila in filas:
                if fila["modelo"] != modelo:
                    raise ValueError(
                        "Modelo incorrecto en archivo"
                    )

            metricas = evaluar(
                filas, etiquetas
            )

            resultado = {
                "modelo": modelo,
                "prompt": estrategia,
                **{
                    clave: metricas[clave]
                    for clave in [
                        "total", "TP", "TN",
                        "FP_penalizado",
                        "FN_penalizado",
                        "precision", "recall",
                        "f1_binario",
                        "f1_macro_presentes",
                        "invalidos",
                        "tasa_invalidos",
                        "tiempo_medio_s",
                        "tiempo_p95_s",
                    ]
                },
            }

            resultados.append(resultado)

            detalle[
                f"{modelo}/{estrategia}"
            ] = metricas

    ganadores = {}

    for modelo in MODELOS:
        candidatos = [
            fila for fila in resultados
            if fila["modelo"] == modelo
        ]

        candidatos.sort(
            key=lambda fila: (
                -fila["f1_binario"],
                fila["invalidos"],
                fila["tiempo_medio_s"],
                fila["prompt"],
            )
        )

        ganadores[modelo] = candidatos[0]["prompt"]

    resumen = {
        "conjunto": "desarrollo",
        "total_eventos": 148,
        "criterio": (
            "Mayor F1 binario penalizado; "
            "desempate por invalidos y latencia."
        ),
        "resultados": resultados,
        "ganadores": ganadores,
        "detalle": detalle,
    }

    CARPETA.mkdir(
        parents=True, exist_ok=True
    )

    with SALIDA.open("x", encoding="utf-8") as archivo:
        json.dump(
            resumen,
            archivo,
            indent=2,
            ensure_ascii=False,
        )

    with SALIDA_CSV.open(
        "x", newline="", encoding="utf-8"
    ) as archivo:
        writer = csv.DictWriter(
            archivo,
            fieldnames=list(resultados[0]),
        )

        writer.writeheader()
        writer.writerows(resultados)

    print("=" * 65)
    print("COMPARACION DE PROMPTS - DEV A2")
    print("=" * 65)

    for fila in resultados:
        print(
            f"{fila['modelo']:<12} "
            f"{fila['prompt']:<18} "
            f"F1={fila['f1_binario']:.4f} "
            f"MacroF1={fila['f1_macro_presentes']:.4f} "
            f"Invalidos={fila['invalidos']:>3} "
            f"Media={fila['tiempo_medio_s']:.4f}s"
        )

    print("\nPROMPTS GANADORES")
    for modelo, prompt in ganadores.items():
        print(f"{modelo}: {prompt}")

    print("\nArchivos:")
    print(SALIDA)
    print(SALIDA_CSV)
    print("\nCOMPARACION FINALIZADA: OK")


if __name__ == "__main__":
    main()

