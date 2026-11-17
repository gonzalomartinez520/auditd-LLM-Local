
import csv
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ESCENARIOS = BASE / "data/raw/escenarios"
SALIDA = BASE / "data/processed/dataset"

FUENTES = [
    ("NORMAL", BASE / "data/processed/normal_eventos_limpios.jsonl", 272, 0),
    ("E1", ESCENARIOS / "e1_eventos_candidatos.jsonl", 32, 0),
    ("E2", ESCENARIOS / "e2_eventos_correlacionados.jsonl", 50, 1),
    ("E3a", ESCENARIOS / "e3a_eventos_correlacionados.jsonl", 20, 0),
    ("E3b_control", ESCENARIOS / "e3b_controles_correlacionados.jsonl", 40, 0),
    ("E3b_ataque", ESCENARIOS / "e3b_ataque_eventos_correlacionados.jsonl", 40, 1),
    ("E4a", ESCENARIOS / "e4a_eventos_correlacionados.jsonl", 10, 0),
    ("E4b", ESCENARIOS / "e4b_eventos_correlacionados.jsonl", 10, 1),
    ("E5a", ESCENARIOS / "e5a_eventos_correlacionados.jsonl", 35, 0),
    ("E5b", ESCENARIOS / "e5b_eventos_correlacionados.jsonl", 10, 1),
]


def leer_jsonl(ruta):
    eventos = []

    with ruta.open(encoding="utf-8") as archivo:
        for numero_linea, linea in enumerate(archivo, 1):
            if not linea.strip():
                continue

            try:
                eventos.append(json.loads(linea))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{ruta}:{numero_linea}: {error}"
                ) from error

    return eventos


def construir():
    eventos_unificados = []
    etiquetas = []
    ids_globales = set()

    por_fuente = {}
    por_clase = Counter()

    for nombre, ruta, esperado, etiqueta in FUENTES:
        if not ruta.is_file():
            raise ValueError(f"Falta el archivo: {ruta}")

        eventos = leer_jsonl(ruta)

        if len(eventos) != esperado:
            raise ValueError(
                f"{nombre}: esperados={esperado}, "
                f"obtenidos={len(eventos)}"
            )

        por_fuente[nombre] = len(eventos)

        for evento in eventos:
            event_id = evento.get("event_id")
            records = evento.get("records")

            if not isinstance(event_id, str) or not event_id:
                raise ValueError(
                    f"{nombre}: event_id invalido"
                )

            if event_id in ids_globales:
                raise ValueError(
                    f"Identificador duplicado: {event_id}"
                )

            if not isinstance(records, list):
                raise ValueError(
                    f"{nombre}: records no es una lista"
                )

            if not all(isinstance(r, str) for r in records):
                raise ValueError(
                    f"{nombre}: records contiene "
                    "elementos no textuales"
                )

            if not records:
                raise ValueError(
                    f"{nombre}: evento sin registros"
                )

            etiqueta_existente = evento.get("amenaza")

            if etiqueta_existente is not None:
                try:
                    valor = int(etiqueta_existente)
                except (ValueError, TypeError) as error:
                    raise ValueError(
                        f"{nombre}: etiqueta invalida"
                    ) from error

                if valor != etiqueta:
                    raise ValueError(
                        f"{nombre}: contradiccion de etiquetas "
                        f"en evento {event_id}"
                    )

            if nombre == "NORMAL":
                intervalo = evento.get("intervalo")

                if not isinstance(intervalo, str) or not intervalo:
                    raise ValueError(
                        "NORMAL: falta intervalo"
                    )

                grupo = f"NORMAL:{intervalo}"
                repeticion = ""
                criterio = "referencia_normal_provisional"

            else:
                repeticion = evento.get("repeticion")

                if type(repeticion) is not int:
                    raise ValueError(
                        f"{nombre}: repeticion invalida"
                    )

                if not 1 <= repeticion <= 10:
                    raise ValueError(
                        f"{nombre}: repeticion fuera de rango"
                    )

                grupo = f"{nombre}:{repeticion}"
                criterio = "etiqueta_por_escenario"

            ids_globales.add(event_id)
            por_clase[etiqueta] += 1

            # No se incluyen campos experimentales.
            eventos_unificados.append({
                "event_id": event_id,
                "records": records,
            })

            # Referencia de etiquetas, separada de los eventos.
            etiquetas.append({
                "event_id": event_id,
                "fuente": nombre,
                "repeticion": repeticion,
                "grupo": grupo,
                "amenaza": etiqueta,
                "criterio": criterio,
            })

    if (
        len(eventos_unificados) != 519
        or por_clase[0] != 409
        or por_clase[1] != 110
    ):
        raise ValueError(
            "Las cantidades globales no coinciden."
        )

    if SALIDA.exists() and any(SALIDA.iterdir()):
        raise ValueError(
            "El directorio de salida ya contiene archivos. "
            "No se sobrescribiran."
        )

    SALIDA.mkdir(parents=True, exist_ok=True)

    ruta_eventos = SALIDA / "eventos_unificados.jsonl"
    ruta_etiquetas = SALIDA / "etiquetas.csv"
    ruta_resumen = SALIDA / "resumen_dataset.json"

    with ruta_eventos.open("x", encoding="utf-8") as archivo:
        for evento in eventos_unificados:
            archivo.write(
                json.dumps(evento, ensure_ascii=False) + "\n"
            )

    with ruta_etiquetas.open(
        "x", newline="", encoding="utf-8"
    ) as archivo:
        writer = csv.DictWriter(
            archivo,
            fieldnames=[
                "event_id",
                "fuente",
                "repeticion",
                "grupo",
                "amenaza",
                "criterio",
            ],
        )
        writer.writeheader()
        writer.writerows(etiquetas)

    resumen = {
        "total_eventos": len(eventos_unificados),
        "identificadores_unicos": len(ids_globales),
        "duplicados": 0,
        "eventos_por_fuente": por_fuente,
        "eventos_por_clase": {
            "legitimos_referencia": por_clase[0],
            "sospechosos_simulados": por_clase[1],
        },
        "cantidad_grupos": len({
            e["grupo"] for e in etiquetas
        }),
        "etiquetado": "contextual_experimental",
        "normal_etiqueta": "provisional",
    }

    with ruta_resumen.open("x", encoding="utf-8") as archivo:
        json.dump(resumen, archivo, indent=2, ensure_ascii=False)

    print("=" * 54)
    print("CONSTRUCCION DEL DATASET A2")
    print("=" * 54)

    for nombre, cantidad in por_fuente.items():
        print(f"{nombre:<18} {cantidad:>5} eventos")

    print("-" * 54)
    print("Total eventos:", len(eventos_unificados))
    print("Identificadores unicos:", len(ids_globales))
    print("Duplicados:", 0)
    print("Referencia legitima:", por_clase[0])
    print("Sospechosos simulados:", por_clase[1])
    print("Grupos:", resumen["cantidad_grupos"])
    print("VALIDACION GENERAL: OK")
    print("\nArchivos generados en:", SALIDA)


if __name__ == "__main__":
    construir()

