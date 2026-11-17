
import json
import time
import urllib.request
from pathlib import Path

from config_llm_a2 import (
    URL_OLLAMA,
    MODELOS,
    ESTRATEGIAS,
    OPCIONES,
    ESQUEMA_RESPUESTA,
    validar_prediccion,
)
from prompts_llm import (
    cargar_desarrollo,
    construir_prompt,
)

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "results/piloto_prompts_a2_v2.jsonl"

# Margen conservador antes de las llamadas.
# Es una comprobacion de tamano, no un tokenizer.
MAX_BYTES_PROMPT = 6000
MAX_TOKENS_ENTRADA = (
    OPCIONES["num_ctx"] - OPCIONES["num_predict"]
)


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
        data=json.dumps(
            solicitud
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    inicio = time.perf_counter()

    with urllib.request.urlopen(
        peticion, timeout=300
    ) as respuesta:
        datos = json.load(respuesta)

    tiempo = time.perf_counter() - inicio

    try:
        prediccion = json.loads(
            datos.get("response", "")
        )
        valido = validar_prediccion(prediccion)
    except (json.JSONDecodeError, TypeError):
        prediccion = None
        valido = False

    tokens = datos.get("prompt_eval_count")
    margen_ok = (
        isinstance(tokens, int)
        and tokens < MAX_TOKENS_ENTRADA
    )

    return {
        "prediccion": prediccion,
        "valido": valido,
        "tiempo_s": round(tiempo, 4),
        "prompt_eval_count": tokens,
        "eval_count": datos.get("eval_count"),
        "total_duration_s": (
            datos.get("total_duration", 0) / 1e9
        ),
        "load_duration_s": (
            datos.get("load_duration", 0) / 1e9
        ),
        "margen_contexto_ok": margen_ok,
    }


def main():
    if SALIDA.exists():
        raise SystemExit(
            "ERROR: ya existe el archivo del piloto. "
            "No se sobrescribira."
        )

    desarrollo = cargar_desarrollo()
    objetivo = desarrollo[0]

    prompts = {}

    for estrategia in ESTRATEGIAS:
        construido = construir_prompt(
            estrategia, objetivo, desarrollo
        )

        cantidad_bytes = len(
            construido["prompt"].encode("utf-8")
        )

        if cantidad_bytes > MAX_BYTES_PROMPT:
            raise ValueError(
                f"Prompt {estrategia} demasiado grande "
                f"para la comprobacion conservadora: "
                f"{cantidad_bytes} bytes"
            )

        prompts[estrategia] = construido

    # La comprobacion anterior debe ampliarse a
    # todos los eventos antes de la evaluacion completa.
    SALIDA.parent.mkdir(
        parents=True, exist_ok=True
    )

    print("=" * 60)
    print("PILOTO DE PROMPTS - TP FINAL A2")
    print("=" * 60)
    print("Evento seleccionado:", objetivo["event_id"])

    with SALIDA.open("x", encoding="utf-8") as archivo:
        for modelo in MODELOS:
            for estrategia in ESTRATEGIAS:
                construido = prompts[estrategia]

                print(
                    f"\nModelo: {modelo}"
                    f" | Prompt: {estrategia}",
                    flush=True,
                )

                respuesta = consultar(
                    modelo,
                    construido["prompt"],
                )

                fila = {
                    "serial": objetivo[
                        "event_id"
                    ].rsplit(":", 1)[1],
                    "event_id": objetivo["event_id"],
                    "modelo": modelo,
                    "estrategia": estrategia,
                    "ejemplos": construido["ids_ejemplos"],
                    **respuesta,
                }

                archivo.write(
                    json.dumps(
                        fila,
                        ensure_ascii=False,
                    ) + "\n"
                )
                archivo.flush()

                print(
                    "JSON valido:",
                    respuesta["valido"]
                )
                print(
                    "Nivel:",
                    (
                        respuesta["prediccion"].get("nivel")
                        if isinstance(
                            respuesta["prediccion"], dict
                        )
                        else None
                    )
                )
                print(
                    "Tiempo:",
                    respuesta["tiempo_s"],
                    "s",
                )
                print(
                    "Tokens de entrada:",
                    respuesta["prompt_eval_count"]
                )
                print(
                    "Tokens de salida:",
                    respuesta["eval_count"]
                )
                print(
                    "Margen de contexto:",
                    "OK"
                    if respuesta["margen_contexto_ok"]
                    else "REVISAR"
                )

    print("\nPILOTO FINALIZADO")
    print("Archivo:", SALIDA)


if __name__ == "__main__":
    main()

