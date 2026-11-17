
import json
from collections import Counter
from pathlib import Path

from config_llm_a2 import MODELOS, OPCIONES

BASE = Path(__file__).resolve().parent.parent
RESULTS = BASE / "results/llm_dev"

ESTRATEGIAS = {
    "zero_shot": 158,
    "few_shot": 158,
    "chain_of_thought": 158,
    "few_shot_fijo": 148,
}

CONTEXTO = OPCIONES["num_ctx"]
RESERVA = OPCIONES["num_predict"]
LIMITE = CONTEXTO - RESERVA


def cargar_jsonl(ruta):
    filas = []

    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if linea.strip():
                filas.append(json.loads(linea))

    return filas


def main():
    print("=" * 65)
    print("AUDITORIA DE CONTEXTO LLM - DEV A2")
    print("=" * 65)

    print("num_ctx:", CONTEXTO)
    print("num_predict:", RESERVA)
    print("Presupuesto preventivo entrada:", LIMITE)

    errores = []

    for modelo in MODELOS:
        nombre = modelo.replace(":", "_")

        for estrategia, esperado in ESTRATEGIAS.items():
            ruta = RESULTS / (
                f"{nombre}_{estrategia}.jsonl"
            )

            if not ruta.exists():
                errores.append(
                    f"Archivo faltante: {ruta}"
                )
                continue

            filas = cargar_jsonl(ruta)
            ids = [fila["event_id"] for fila in filas]

            tokens = [
                fila.get("prompt_eval_count")
                for fila in filas
            ]

            faltantes = sum(
                type(valor) is not int
                or valor < 0
                for valor in tokens
            )

            conocidos = [
                valor for valor in tokens
                if type(valor) is int and valor >= 0
            ]

            cercanos = sum(
                valor >= LIMITE
                for valor in conocidos
            )

            marcados = sum(
                bool(fila.get("contexto_revisar"))
                for fila in filas
            )

            terminados = len(set(ids)) == len(ids)

            configuraciones = {
                fila.get("hash_config")
                for fila in filas
            }

            hashes_prompt = sum(
                bool(fila.get("hash_prompt"))
                for fila in filas
            )

            maximo = max(conocidos) if conocidos else None
            minimo = min(conocidos) if conocidos else None
            promedio = (
                sum(conocidos) / len(conocidos)
                if conocidos else None
            )

            print("\n" + "-" * 65)
            print("Modelo:", modelo)
            print("Prompt:", estrategia)
            print("Eventos:", len(filas), "/", esperado)
            print("IDs únicos:", terminados)
            print("Tokens mínimos:", minimo)
            print("Tokens máximos:", maximo)
            print(
                "Tokens promedio:",
                round(promedio, 2)
                if promedio is not None else None
            )
            print("Sin contador:", faltantes)
            print("Sobre presupuesto:", cercanos)
            print("Contexto marcado:", marcados)
            print(
                "Hashes config distintos:",
                len(configuraciones)
            )
            print(
                "Hashes prompt presentes:",
                hashes_prompt,
            )

            if len(filas) != esperado or not terminados:
                errores.append(
                    f"{modelo}/{estrategia}: eventos incorrectos"
                )

            if faltantes or cercanos or marcados:
                errores.append(
                    f"{modelo}/{estrategia}: revisar contexto"
                )

            if (
                len(configuraciones) != 1
                or None in configuraciones
                or hashes_prompt != esperado
            ):
                errores.append(
                    f"{modelo}/{estrategia}: hashes incompletos"
                )

    print("\n" + "=" * 65)

    if errores:
        print("AUDITORIA: REVISAR")

        for error in errores:
            print("-", error)
    else:
        print("AUDITORIA DE CONTADORES: OK")
        print(
            "Los resultados registrados respetan "
            "el presupuesto preventivo."
        )
        print(
            "Esto no constituye por si solo "
            "una prueba de ausencia de truncamiento."
        )


if __name__ == "__main__":
    main()

