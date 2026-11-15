
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/raw/escenarios"

ESPERADOS = {
    "E1": 32,
    "E2": 50,
    "E3a": 20,
    "E3b_control": 40,
    "E3b_ataque": 40,
    "E4a": 10,
    "E4b": 10,
    "E5a": 35,
    "E5b": 10,
}

DESCRIPCIONES = {
    "E1": "Consultas legitimas",
    "E2": "Comprobaciones de privilegios",
    "E3a": "Administracion legitima",
    "E3b_control": "Controles de privilegios",
    "E3b_ataque": "Simulacion de privilegios",
    "E4a": "Modificacion legitima",
    "E4b": "Modificacion simulada",
    "E5a": "Lectura legitima",
    "E5b": "Lectura sospechosa simulada",
}


def identificar(nombre):
    nombre = nombre.lower()

    if nombre.startswith("e3b_ataque"):
        return "E3b_ataque"

    if nombre.startswith("e3b"):
        return "E3b_control"

    match = re.match(r"^(e1|e2|e3a|e4a|e4b|e5a|e5b)_", nombre)

    if match:
        return match.group(1).replace("e", "E", 1)

    return None


def contar_eventos(ruta):
    cantidad = 0

    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            json.loads(linea)
            cantidad += 1

    return cantidad


def main():
    archivos = {}

    for ruta in sorted(DATA.glob("*.jsonl")):
        grupo = identificar(ruta.name)

        if grupo is None:
            continue

        archivos.setdefault(grupo, []).append(ruta)

    resultados = {}
    problemas = []

    for grupo, esperado in ESPERADOS.items():
        candidatos = archivos.get(grupo, [])

        if len(candidatos) != 1:
            problemas.append(
                f"{grupo}: se encontraron "
                f"{len(candidatos)} archivos JSONL"
            )
            continue

        ruta = candidatos[0]
        cantidad = contar_eventos(ruta)

        resultados[grupo] = cantidad

        if cantidad != esperado:
            problemas.append(
                f"{grupo}: esperado={esperado}, "
                f"obtenido={cantidad}"
            )

    print("=" * 73)
    print(" TP FINAL A2 - RESUMEN GENERAL DE ESCENARIOS")
    print("=" * 73)

    print(
        f'{"Escenario":<15}'
        f'{"Descripcion":<37}'
        f'{"Eventos":>10}'
    )

    print("-" * 73)

    for grupo, cantidad in resultados.items():
        print(
            f"{grupo:<15}"
            f"{DESCRIPCIONES[grupo]:<37}"
            f"{cantidad:>10}"
        )

    print("-" * 73)

    total = sum(resultados.values())

    print(
        f'{"TOTAL":<52}'
        f'{total:>10}'
    )

    print("=" * 73)

    if problemas:
        print("\nVALIDACION: REVISAR")

        for problema in problemas:
            print(" -", problema)

        raise SystemExit(1)

    print("\nArchivos JSONL analizados:", len(resultados))
    print("Eventos correlacionados:", total)
    print("Variantes completadas: 8 de 8")
    print("VALIDACION GENERAL: OK")


if __name__ == "__main__":
    main()

