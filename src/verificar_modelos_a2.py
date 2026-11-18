
import json
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

CONGELADO = BASE / "docs/protocolo_test_a2.json"
URL_MODELOS = "http://127.0.0.1:11434/api/tags"


def main():
    with CONGELADO.open(encoding="utf-8") as archivo:
        protocolo = json.load(archivo)

    with urllib.request.urlopen(
        URL_MODELOS, timeout=15
    ) as respuesta:
        datos = json.load(respuesta)

    disponibles = {
        modelo["name"]: modelo
        for modelo in datos["models"]
    }

    print("=" * 60)
    print("VERIFICACION DE MODELOS OLLAMA - A2")
    print("=" * 60)

    errores = []

    for nombre, configuracion in protocolo["modelos"].items():
        esperado = configuracion["id"]

        if nombre not in disponibles:
            errores.append(
                f"Modelo no instalado: {nombre}"
            )
            continue

        instalado = disponibles[nombre]
        digest = instalado["digest"]

        coincide = digest.startswith(esperado)

        print("\nModelo:", nombre)
        print("ID esperado:", esperado)
        print("Digest instalado:", digest)
        print(
            "Identidad:",
            "OK" if coincide else "NO COINCIDE"
        )

        if not coincide:
            errores.append(
                f"Digest diferente: {nombre}"
            )

    print("\n" + "=" * 60)

    if errores:
        for error in errores:
            print("ERROR:", error)

        raise SystemExit(
            "VERIFICACION DE MODELOS: FALLIDA"
        )

    print("VERIFICACION DE MODELOS: OK")


if __name__ == "__main__":
    main()

