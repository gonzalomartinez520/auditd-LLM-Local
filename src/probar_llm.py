
import csv
import json
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/processed/dataset"
RESULTS = BASE / "results"

DEV = DATA / "desarrollo.jsonl"
ETIQUETAS = DATA / "etiquetas.csv"
SALIDA = RESULTS / "qwen3_piloto_dev.json"

MODELO = "qwen3:0.6b"
URL = "http://127.0.0.1:11434/api/generate"

FUENTES_PILOTO = [
    "NORMAL",
    "E2",
    "E3b_ataque",
    "E5a",
    "E5b",
]

PROMPT = """Eres un analizador de eventos de auditoria
de Linux.

Clasifica el evento como:
- LEGITIMO: no hay evidencia suficiente de actividad sospechosa.
- SOSPECHOSO: existen indicadores concretos de un
  comportamiento que requiere investigacion de seguridad.

Ten en cuenta:
- Una operacion administrativa como passwd o chage
  puede ser legitima.
- Tener privilegios root no demuestra un ataque.
- Una autenticacion fallida puede indicar un intento
  de acceso no autorizado.
- Una combinacion anomala de UID y EUID puede ser
  relevante.
- Los accesos a archivos sensibles deben evaluarse
  segun el proceso y el contexto disponible.
- No inventes informacion ausente del registro.

Responde solamente un objeto JSON con:
{"clasificacion": "LEGITIMO" o "SOSPECHOSO"}

EVENTO:
"""


def cargar_etiquetas():
    with ETIQUETAS.open(
        newline="", encoding="utf-8"
    ) as archivo:
        return {
            fila["event_id"]: fila
            for fila in csv.DictReader(archivo)
        }


def seleccionar_eventos(etiquetas):
    seleccionados = {}

    with DEV.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            evento = json.loads(linea)
            identificador = evento["event_id"]
            fuente = etiquetas[identificador]["fuente"]

            if (
                fuente in FUENTES_PILOTO
                and fuente not in seleccionados
            ):
                seleccionados[fuente] = evento

    faltantes = set(FUENTES_PILOTO) - set(seleccionados)

    if faltantes:
        raise ValueError(
            f"Faltan fuentes: {sorted(faltantes)}"
        )

    return [
        (fuente, seleccionados[fuente])
        for fuente in FUENTES_PILOTO
    ]


def consultar_modelo(texto):
    datos = {
        "model": MODELO,
        "prompt": PROMPT + texto,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_ctx": 2048,
            "num_predict": 64,
        },
    }

    solicitud = urllib.request.Request(
        URL,
        data=json.dumps(datos).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    inicio = time.perf_counter()

    with urllib.request.urlopen(
        solicitud, timeout=240
    ) as respuesta:
        resultado = json.load(respuesta)

    duracion_local = time.perf_counter() - inicio

    respuesta_texto = resultado.get("response", "")

    try:
        respuesta_json = json.loads(respuesta_texto)
        clasificacion = respuesta_json.get(
            "clasificacion"
        )
    except (json.JSONDecodeError, AttributeError):
        clasificacion = None

    if not isinstance(clasificacion, str):
        clasificacion = "INVALIDA"
    else:
        clasificacion = clasificacion.strip().upper()

    if clasificacion not in {
        "LEGITIMO", "SOSPECHOSO"
    }:
        clasificacion = "INVALIDA"

    return {
        "clasificacion": clasificacion,
        "respuesta_original": respuesta_texto,
        "tiempo_local_s": round(duracion_local, 4),
        "total_duration_s": (
            resultado.get("total_duration", 0) / 1e9
        ),
        "load_duration_s": (
            resultado.get("load_duration", 0) / 1e9
        ),
        "prompt_eval_count": resultado.get(
            "prompt_eval_count"
        ),
        "eval_count": resultado.get("eval_count"),
        "eval_duration_s": (
            resultado.get("eval_duration", 0) / 1e9
        ),
        "done": resultado.get("done"),
    }


def main():
    if SALIDA.exists():
        raise SystemExit(
            f"ERROR: ya existe {SALIDA}"
        )

    etiquetas = cargar_etiquetas()
    seleccionados = seleccionar_eventos(etiquetas)

    resultados = []

    print("=" * 56)
    print("PRUEBA PILOTO LLM - QWEN3 0.6B")
    print("=" * 56)

    for fuente, evento in seleccionados:
        identificador = evento["event_id"]

        print(
            f"\nConsultando {fuente}...",
            flush=True,
        )

        prediccion = consultar_modelo(
            evento["texto"]
        )

        etiqueta = int(
            etiquetas[identificador]["amenaza"]
        )

        esperado = (
            "SOSPECHOSO"
            if etiqueta == 1
            else "LEGITIMO"
        )

        correcto = (
            prediccion["clasificacion"] == esperado
        )

        resultados.append({
            "event_id": identificador,
            "fuente": fuente,
            "etiqueta_real": etiqueta,
            "esperado": esperado,
            "correcto": correcto,
            **prediccion,
        })

        print("Esperado:", esperado)
        print(
            "Prediccion:",
            prediccion["clasificacion"]
        )
        print("Correcto:", correcto)
        print(
            "Tiempo total (s):",
            prediccion["tiempo_local_s"]
        )
        print(
            "Tokens generados:",
            prediccion["eval_count"]
        )

    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    with SALIDA.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            {
                "modelo": MODELO,
                "conjunto": "desarrollo",
                "tipo": "piloto",
                "num_ctx": 2048,
                "num_predict": 64,
                "temperature": 0,
                "resultados": resultados,
            },
            archivo,
            indent=2,
            ensure_ascii=False,
        )

    correctos = sum(
        r["correcto"] for r in resultados
    )

    invalidos = sum(
        r["clasificacion"] == "INVALIDA"
        for r in resultados
    )

    print("\n" + "=" * 56)
    print("RESUMEN DEL PILOTO")
    print("=" * 56)

    print("Eventos evaluados:", len(resultados))
    print("Clasificaciones correctas:", correctos)
    print("Respuestas invalidas:", invalidos)

    print("Archivo:", SALIDA)
    print("\nPRUEBA PILOTO FINALIZADA")


if __name__ == "__main__":
    main()

