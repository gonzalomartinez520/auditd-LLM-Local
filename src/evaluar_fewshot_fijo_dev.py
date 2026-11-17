
import argparse
import hashlib
import json
import urllib.error
from pathlib import Path

from config_llm_a2 import (
    MODELOS,
    OPCIONES,
    ESQUEMA_RESPUESTA,
)
from prompts_llm import cargar_desarrollo
from prompts_fewshot_fijo import (
    cargar_protocolo,
    construir_fewshot_fijo,
)
from evaluar_prompts_dev import (
    consultar,
    calcular_metricas,
    hash_objeto,
)

BASE = Path(__file__).resolve().parent.parent
RESULTS = BASE / "results/llm_dev"


def sha256(texto):
    return hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()


def cargar_previos(ruta):
    filas = {}

    if not ruta.exists():
        return filas

    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            fila = json.loads(linea)
            identificador = fila["event_id"]

            if identificador in filas:
                raise ValueError(
                    "Prediccion duplicada: " + identificador
                )

            filas[identificador] = fila

    return filas


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--modelo",
        required=True,
        choices=MODELOS,
    )

    args = parser.parse_args()
    modelo = args.modelo

    nombre = modelo.replace(":", "_")

    salida = RESULTS / (
        f"{nombre}_few_shot_fijo.jsonl"
    )

    resumen_ruta = RESULTS / (
        f"{nombre}_few_shot_fijo_resumen.json"
    )

    if resumen_ruta.exists():
        raise SystemExit(
            "Ya existe el resumen final: "
            + str(resumen_ruta)
        )

    desarrollo = cargar_desarrollo()
    protocolo, ejemplos = cargar_protocolo(desarrollo)

    por_id = {
        e["event_id"]: e for e in desarrollo
    }

    ids = protocolo["ids_evaluacion"]

    trabajos = {}

    for identificador in ids:
        evento = por_id[identificador]

        prompt = construir_fewshot_fijo(
            evento, ejemplos
        )

        if len(prompt.encode("utf-8")) > 12000:
            raise ValueError(
                "Prompt supera limite preventivo: "
                + identificador
            )

        trabajos[identificador] = {
            "prompt": prompt,
            "hash_prompt": sha256(prompt),
        }

    configuracion = {
        "modelo": modelo,
        "estrategia": "few_shot_fijo_v1",
        "opciones": OPCIONES,
        "formato": ESQUEMA_RESPUESTA,
        "ids_ejemplos": protocolo["ids_ejemplos"],
        "ids_evaluacion": ids,
    }

    hash_config = hash_objeto(configuracion)

    previos = cargar_previos(salida)

    if not set(previos).issubset(set(ids)):
        raise ValueError(
            "Resultados previos fuera de la evaluacion"
        )

    for identificador, fila in previos.items():
        if (
            fila["hash_config"] != hash_config
            or fila["hash_prompt"]
            != trabajos[identificador]["hash_prompt"]
        ):
            raise ValueError(
                "La configuracion cambio: "
                + identificador
            )

        if fila.get("contexto_revisar"):
            raise ValueError(
                "Hay un resultado previo con contexto "
                "pendiente de revision: " + identificador
            )

    RESULTS.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("FEW-SHOT FIJO - DESARROLLO A2")
    print("=" * 60)
    print("Modelo:", modelo)
    print("Ejemplos:", protocolo["ids_ejemplos"])
    print("Eventos previstos:", len(ids))
    print("Procesados anteriormente:", len(previos))

    with salida.open("a", encoding="utf-8") as archivo:
        for identificador in ids:
            if identificador in previos:
                continue

            evento = por_id[identificador]
            referencia = evento["etiqueta"]

            try:
                respuesta = consultar(
                    modelo,
                    trabajos[identificador]["prompt"],
                )
            except (
                Exception
            ) as error:
                print(
                    "\nError tecnico en",
                    identificador,
                    type(error).__name__,
                    str(error),
                )
                print(
                    "Se conservaron las inferencias anteriores."
                )
                raise SystemExit(1)

            fila = {
                "event_id": identificador,
                "serial": referencia["serial"],
                "modelo": modelo,
                "estrategia": "few_shot_fijo_v1",
                "fuente": referencia["fuente"],
                "real_amenaza": int(referencia["amenaza"]),
                "real_nivel": referencia["nivel"],
                "real_tipo": referencia["tipo"],
                "ids_ejemplos": protocolo["ids_ejemplos"],
                "hash_prompt":
                    trabajos[identificador]["hash_prompt"],
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

            if len(previos) % 10 == 0 or len(previos) == len(ids):
                print(
                    f"Procesados: {len(previos)}/{len(ids)}",
                    flush=True,
                )

            if respuesta["contexto_revisar"]:
                print(
                    "\nREVISAR CONTEXTO:",
                    identificador,
                )
                print(
                    "No se continuara hasta resolverlo."
                )
                raise SystemExit(2)

    if len(previos) != len(ids):
        raise ValueError("Evaluacion incompleta")

    filas = [previos[identificador] for identificador in ids]

    metricas = calcular_metricas(filas)

    resumen = {
        "configuracion": configuracion,
        "hash_config": hash_config,
        "conjunto": "desarrollo_148",
        "metricas": metricas,
        "nota": (
            "Las respuestas invalidas cuentan como "
            "errores de clasificacion."
        ),
    }

    with resumen_ruta.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            resumen,
            archivo,
            indent=2,
            ensure_ascii=False,
        )

    print("\n" + "=" * 60)
    print("RESULTADOS FEW-SHOT FIJO")
    print("=" * 60)

    for campo in (
        "TP",
        "TN",
        "FP_penalizado",
        "FN_penalizado",
        "invalidos",
    ):
        print(f"{campo}: {metricas[campo]}")

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

    print("\nEVALUACION FEW-SHOT FIJO: OK")


if __name__ == "__main__":
    main()

