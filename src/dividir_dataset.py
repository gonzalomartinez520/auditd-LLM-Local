
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/processed/dataset"

EVENTOS = DATA / "eventos_normalizados.jsonl"
ETIQUETAS = DATA / "etiquetas.csv"

DESARROLLO = DATA / "desarrollo.jsonl"
PRUEBA = DATA / "prueba.jsonl"
ASIGNACIONES = DATA / "asignaciones.csv"
RESUMEN = DATA / "resumen_division.json"

TOTAL_ESPERADO = 519
SEMILLA = 42

# Tres repeticiones completas de cada variante en dev.
REPETICIONES_DEV = {1, 2, 3}

# Treinta por ciento de los 272 eventos normales.
PORCENTAJE_RUIDO_DEV = 0.30

FUENTES = {
    "E1", "E2", "E3a",
    "E3b_control", "E3b_ataque",
    "E4a", "E4b", "E5a", "E5b",
}


def leer_jsonl(ruta):
    eventos = {}

    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            evento = json.loads(linea)
            identificador = evento["event_id"]

            if identificador in eventos:
                raise ValueError(
                    f"Evento duplicado: {identificador}"
                )

            eventos[identificador] = evento

    return eventos


def leer_etiquetas():
    etiquetas = {}

    with ETIQUETAS.open(
        newline="", encoding="utf-8"
    ) as archivo:
        for fila in csv.DictReader(archivo):
            identificador = fila["event_id"]

            if identificador in etiquetas:
                raise ValueError(
                    f"Etiqueta duplicada: {identificador}"
                )

            etiquetas[identificador] = fila

    return etiquetas


def main():
    for ruta in (
        DESARROLLO, PRUEBA, ASIGNACIONES, RESUMEN
    ):
        if ruta.exists():
            raise SystemExit(
                f"ERROR: ya existe {ruta}. "
                "No se sobrescribira."
            )

    eventos = leer_jsonl(EVENTOS)
    etiquetas = leer_etiquetas()

    if (
        len(eventos) != TOTAL_ESPERADO
        or len(etiquetas) != TOTAL_ESPERADO
        or set(eventos) != set(etiquetas)
    ):
        raise ValueError(
            "Eventos y etiquetas inconsistentes."
        )

    # Seleccion reproducible de eventos normales.
    ids_normales = sorted(
        identificador
        for identificador, fila in etiquetas.items()
        if fila["fuente"] == "NORMAL"
    )

    if len(ids_normales) != 272:
        raise ValueError(
            "Cantidad inesperada de ruido normal."
        )

    cantidad_ruido_dev = round(
        len(ids_normales) * PORCENTAJE_RUIDO_DEV
    )

    generador = random.Random(SEMILLA)

    ruido_dev = set(
        generador.sample(
            ids_normales,
            cantidad_ruido_dev,
        )
    )

    conjuntos = {
        "desarrollo": [],
        "prueba": [],
    }

    conteos = defaultdict(Counter)
    repeticiones_por_conjunto = defaultdict(
        lambda: defaultdict(set)
    )

    asignaciones = []
    grupo_destino = {}

    for identificador, evento in eventos.items():
        fila = etiquetas[identificador]
        fuente = fila["fuente"]
        grupo = fila["grupo"]
        amenaza = int(fila["amenaza"])

        if amenaza not in (0, 1):
            raise ValueError(
                f"Etiqueta invalida: {identificador}"
            )

        if fuente == "NORMAL":
            conjunto = (
                "desarrollo"
                if identificador in ruido_dev
                else "prueba"
            )

        elif fuente in FUENTES:
            repeticion = int(fila["repeticion"])

            if not 1 <= repeticion <= 10:
                raise ValueError(
                    f"Repeticion invalida: {repeticion}"
                )

            if grupo != f"{fuente}:{repeticion}":
                raise ValueError(
                    f"Grupo inconsistente: {grupo}"
                )

            conjunto = (
                "desarrollo"
                if repeticion in REPETICIONES_DEV
                else "prueba"
            )

            if (
                grupo in grupo_destino
                and grupo_destino[grupo] != conjunto
            ):
                raise ValueError(
                    f"Grupo dividido: {grupo}"
                )

            grupo_destino[grupo] = conjunto

            repeticiones_por_conjunto[conjunto][
                fuente
            ].add(repeticion)

        else:
            raise ValueError(
                f"Fuente desconocida: {fuente}"
            )

        conjuntos[conjunto].append(evento)

        conteos[conjunto]["total"] += 1
        conteos[conjunto][f"clase_{amenaza}"] += 1
        conteos[conjunto][fuente] += 1

        asignaciones.append({
            "event_id": identificador,
            "conjunto": conjunto,
            "fuente": fuente,
            "grupo_original": grupo,
            "amenaza": amenaza,
        })

    # Verificar las repeticiones de cada variante.
    for fuente in FUENTES:
        if (
            repeticiones_por_conjunto["desarrollo"][fuente]
            != REPETICIONES_DEV
        ):
            raise ValueError(
                f"Repeticiones dev incorrectas: {fuente}"
            )

        if (
            repeticiones_por_conjunto["prueba"][fuente]
            != set(range(1, 11)) - REPETICIONES_DEV
        ):
            raise ValueError(
                f"Repeticiones test incorrectas: {fuente}"
            )

    if (
        conteos["desarrollo"]["NORMAL"]
        != cantidad_ruido_dev
        or conteos["prueba"]["NORMAL"]
        != len(ids_normales) - cantidad_ruido_dev
    ):
        raise ValueError(
            "Division del ruido incorrecta."
        )

    if (
        len(conjuntos["desarrollo"])
        + len(conjuntos["prueba"])
        != TOTAL_ESPERADO
    ):
        raise ValueError(
            "Se perdieron eventos."
        )

    resumen = {
        "total_eventos": TOTAL_ESPERADO,
        "semilla": SEMILLA,
        "repeticiones_dev": sorted(REPETICIONES_DEV),
        "repeticiones_test": sorted(
            set(range(1, 11)) - REPETICIONES_DEV
        ),
        "porcentaje_ruido_dev_solicitado": 30,
        "ruido_dev": cantidad_ruido_dev,
        "ruido_test": (
            len(ids_normales) - cantidad_ruido_dev
        ),
        "conjuntos": {},
        "separacion": (
            "por_repeticion_en_escenarios_"
            "y_por_evento_en_ruido"
        ),
    }

    for nombre in ("desarrollo", "prueba"):
        resumen["conjuntos"][nombre] = {
            "eventos": conteos[nombre]["total"],
            "clase_0": conteos[nombre]["clase_0"],
            "clase_1": conteos[nombre]["clase_1"],
            "por_fuente": {
                fuente: conteos[nombre][fuente]
                for fuente in ["NORMAL"] + sorted(FUENTES)
            },
        }

    # Generar archivos solamente tras validar.
    for nombre, ruta in (
        ("desarrollo", DESARROLLO),
        ("prueba", PRUEBA),
    ):
        with ruta.open(
            "x", encoding="utf-8"
        ) as archivo:
            for evento in conjuntos[nombre]:
                archivo.write(
                    json.dumps(
                        evento, ensure_ascii=False
                    ) + "\n"
                )

    with ASIGNACIONES.open(
        "x", newline="", encoding="utf-8"
    ) as archivo:
        writer = csv.DictWriter(
            archivo,
            fieldnames=[
                "event_id",
                "conjunto",
                "fuente",
                "grupo_original",
                "amenaza",
            ],
        )
        writer.writeheader()
        writer.writerows(asignaciones)

    with RESUMEN.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            resumen,
            archivo,
            indent=2,
            ensure_ascii=False,
        )

    print("=" * 55)
    print("DIVISION DEL DATASET - CONSIGNA A2")
    print("=" * 55)

    for nombre in ("desarrollo", "prueba"):
        info = resumen["conjuntos"][nombre]

        print(f"\n{nombre.upper()}")
        print("Eventos:", info["eventos"])
        print("Referencia legitima:", info["clase_0"])
        print("Sospechosos simulados:", info["clase_1"])
        print("Ruido:", info["por_fuente"]["NORMAL"])

    print("\nRepeticiones dev por variante: 3")
    print("Repeticiones test por variante: 7")
    print("Ruido dev:", cantidad_ruido_dev)
    print("Ruido test:", len(ids_normales) - cantidad_ruido_dev)
    print("Total:", TOTAL_ESPERADO)
    print("VALIDACION GENERAL: OK")


if __name__ == "__main__":
    main()

