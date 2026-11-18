
import hashlib
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATASET = BASE / "data/processed/dataset"

DEV = DATASET / "desarrollo.jsonl"
TEST = DATASET / "prueba.jsonl"


def leer(ruta):
    eventos = []

    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if linea.strip():
                evento = json.loads(linea)

                eventos.append({
                    "event_id": evento["event_id"],
                    "texto": evento["texto"],
                })

    return eventos


def huella(texto):
    return hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()


def main():
    desarrollo = leer(DEV)
    prueba = leer(TEST)

    ids_dev = {e["event_id"] for e in desarrollo}
    ids_test = {e["event_id"] for e in prueba}

    hashes_dev = Counter(
        huella(e["texto"]) for e in desarrollo
    )

    hashes_test = Counter(
        huella(e["texto"]) for e in prueba
    )

    compartidos = set(hashes_dev) & set(hashes_test)

    eventos_test_conocidos = sum(
        cantidad
        for hash_texto, cantidad in hashes_test.items()
        if hash_texto in hashes_dev
    )

    eventos_test_nuevos = (
        len(prueba) - eventos_test_conocidos
    )

    print("=" * 60)
    print("AUDITORIA DE SOLAPAMIENTO DEV/TEST - A2")
    print("=" * 60)

    print("Eventos DEV:", len(desarrollo))
    print("Eventos TEST:", len(prueba))
    print(
        "IDs compartidos:",
        len(ids_dev & ids_test)
    )

    print("\nTEXTOS NORMALIZADOS")
    print("Distintos en DEV:", len(hashes_dev))
    print("Distintos en TEST:", len(hashes_test))
    print(
        "Patrones compartidos DEV/TEST:",
        len(compartidos)
    )

    print("\nEVENTOS DE TEST")
    print(
        "Con texto presente en DEV:",
        eventos_test_conocidos
    )
    print(
        "Con texto no presente en DEV:",
        eventos_test_nuevos
    )

    print(
        "Porcentaje de eventos con texto conocido:",
        f"{100 * eventos_test_conocidos / len(prueba):.2f}%"
    )

    print("\nNo se leyeron etiquetas.")
    print("No se ejecutaron modelos.")
    print("AUDITORIA DE SOLAPAMIENTO: OK")


if __name__ == "__main__":
    main()

