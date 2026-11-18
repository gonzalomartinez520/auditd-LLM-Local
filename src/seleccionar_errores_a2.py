
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/processed/dataset"
RESULTS = BASE / "results"
FINAL = RESULTS / "analisis_final"

PLAN = [
    ("regex_multiclase", "E2", "FN", 2),
    ("regex_multiclase", "E4b", "FN", 2),

    ("qwen3:0.6b", "E3b_ataque", "FN", 2),
    ("qwen3:0.6b", "NORMAL", "FP", 2),
    ("qwen3:0.6b", "E1", "FP", 1),
    ("qwen3:0.6b", "E3a", "FP", 1),
    ("qwen3:0.6b", "E3b_control", "FP", 1),
    ("qwen3:0.6b", "E4a", "FP", 1),
    ("qwen3:0.6b", "E5a", "FP", 1),

    ("gemma3:1b", "NORMAL", "FP", 2),
    ("gemma3:1b", "E1", "FP", 1),
    ("gemma3:1b", "E3a", "FP", 1),
    ("gemma3:1b", "E3b_control", "FP", 1),
    ("gemma3:1b", "E4a", "FP", 1),
    ("gemma3:1b", "E5a", "FP", 1),
]


def cargar_jsonl(ruta):
    with ruta.open(encoding="utf-8") as archivo:
        return {
            fila["event_id"]: fila
            for linea in archivo
            if linea.strip()
            for fila in [json.loads(linea)]
        }


def ruta_predicciones(modelo):
    if modelo == "regex_multiclase":
        return (
            RESULTS / "regex_test/"
            "regex_multiclase_corrida_1.jsonl"
        )

    nombre = modelo.replace(":", "_")
    return (
        RESULTS / "llm_test/"
        f"{nombre}_corrida_1.jsonl"
    )


def elegir(candidatos, textos, cantidad):
    seleccion = []
    huellas = set()

    # Preferir patrones de entrada diferentes.
    for fila in candidatos:
        texto = textos[fila["event_id"]]["texto"]
        huella = hashlib.sha256(
            texto.encode("utf-8")
        ).hexdigest()

        if huella not in huellas:
            seleccion.append(fila)
            huellas.add(huella)

        if len(seleccion) == cantidad:
            return seleccion

    # Si no hay suficientes patrones distintos,
    # completar con otros eventos del escenario.
    elegidos = {
        fila["event_id"] for fila in seleccion
    }

    for fila in candidatos:
        if fila["event_id"] not in elegidos:
            seleccion.append(fila)

        if len(seleccion) == cantidad:
            break

    return seleccion


def main():
    destino = FINAL / "errores_representativos.json"

    if destino.exists():
        raise SystemExit(
            "La seleccion ya existe; no se sobrescribira."
        )

    textos = cargar_jsonl(DATA / "prueba.jsonl")

    with (FINAL / "errores_test.csv").open(
        encoding="utf-8", newline=""
    ) as archivo:
        errores = [
            fila for fila in csv.DictReader(archivo)
            if fila["corrida"] == "1"
        ]

    predicciones = {
        modelo: cargar_jsonl(ruta_predicciones(modelo))
        for modelo in {
            item[0] for item in PLAN
        }
    }

    seleccion_final = []

    for modelo, fuente, tipo_error, cantidad in PLAN:
        candidatos = sorted(
            (
                fila for fila in errores
                if fila["modelo"] == modelo
                and fila["fuente"] == fuente
                and fila["error"] == tipo_error
            ),
            key=lambda fila: fila["event_id"]
        )

        seleccionados = elegir(
            candidatos, textos, cantidad
        )

        if len(seleccionados) != cantidad:
            raise ValueError(
                f"Faltan casos: {modelo}/{fuente}/{tipo_error}"
            )

        for fila in seleccionados:
            eid = fila["event_id"]
            pred = predicciones[modelo][eid]["prediccion"]

            seleccion_final.append({
                "modelo": modelo,
                "event_id": eid,
                "fuente": fuente,
                "error": tipo_error,
                "nivel_real": fila["nivel_real"],
                "tipo_real": fila["tipo_real"],
                "nivel_predicho": fila["nivel_predicho"],
                "tipo_predicho": fila["tipo_predicho"],
                "texto_normalizado": textos[eid]["texto"],
                "explicacion_modelo": pred["explicacion"],
            })

    if len(seleccion_final) != 20:
        raise ValueError("Se esperaban 20 casos")

    with destino.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            seleccion_final,
            archivo,
            indent=2,
            ensure_ascii=False
        )

    print("=" * 60)
    print("ERRORES REPRESENTATIVOS - TP A2")
    print("=" * 60)

    for numero, caso in enumerate(seleccion_final, 1):
        print(
            f"\n{numero:02d}. {caso['modelo']} "
            f"{caso['fuente']} {caso['error']}"
        )
        print("Evento:", caso["event_id"])
        print(
            "Nivel:",
            caso["nivel_real"],
            "->",
            caso["nivel_predicho"]
        )
        print(
            "Explicacion:",
            caso["explicacion_modelo"][:350]
        )
        print(
            "Texto:",
            caso["texto_normalizado"][:600]
        )

    print("\nTotal seleccionado:", len(seleccion_final))
    print("Archivo:", destino)
    print("SELECCION DE ERRORES: OK")


if __name__ == "__main__":
    main()

