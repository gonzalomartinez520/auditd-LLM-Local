
import csv
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/processed/dataset"

BORRADOR = DATA / "etiquetas_multiclase_borrador.csv"
ORIGINAL = DATA / "etiquetas.csv"

SALIDA = DATA / "etiquetas_multiclase.csv"
RESUMEN = DATA / "resumen_etiquetas_multiclase.json"

ANOMALIAS_VERIFICADAS = {
    "1794002138.650:1055",
    "1794005005.558:2042",
}

NIVELES_VALIDOS = {"INFO", "BAJO", "MEDIO", "ALTO"}

TIPOS_VALIDOS = {
    "actividad_normal",
    "anomalia_operativa",
    "autenticacion",
    "reconocimiento",
    "anomalia_privilegios",
    "acceso_sensible",
    "modificacion_configuracion",
    "otro",
}

DISTRIBUCION_ESPERADA = {
    "INFO": 409,
    "BAJO": 0,
    "MEDIO": 90,
    "ALTO": 20,
}


def leer_csv(ruta):
    with ruta.open(newline="", encoding="utf-8") as archivo:
        return list(csv.DictReader(archivo))


def main():
    if SALIDA.exists() or RESUMEN.exists():
        raise SystemExit(
            "ERROR: ya existen archivos definitivos. "
            "No se sobrescribiran."
        )

    borrador = leer_csv(BORRADOR)
    originales = leer_csv(ORIGINAL)

    if len(borrador) != 519 or len(originales) != 519:
        raise ValueError(
            "Cantidad inesperada de eventos."
        )

    referencia = {}

    for fila in originales:
        identificador = fila["event_id"]

        if identificador in referencia:
            raise ValueError(
                f"Etiqueta original duplicada: {identificador}"
            )

        referencia[identificador] = fila

    filas = []
    encontrados = set()
    identificadores = set()

    for fila in borrador:
        identificador = fila["event_id"]

        if identificador in identificadores:
            raise ValueError(
                f"Duplicado: {identificador}"
            )

        identificadores.add(identificador)

        if identificador not in referencia:
            raise ValueError(
                f"Falta etiqueta original: {identificador}"
            )

        original = referencia[identificador]

        for campo in ("fuente", "repeticion", "grupo", "amenaza"):
            if fila[campo] != original[campo]:
                raise ValueError(
                    f"Inconsistencia en {campo}: {identificador}"
                )

        nivel = fila["nivel_propuesto"]
        tipo = fila["tipo_propuesto"]

        if identificador in ANOMALIAS_VERIFICADAS:
            if (
                fila["fuente"] != "NORMAL"
                or nivel != "INFO"
                or fila["amenaza"] != "0"
                or fila["requiere_revision"] != "1"
            ):
                raise ValueError(
                    f"Anomalia inesperada: {identificador}"
                )

            tipo = "anomalia_operativa"
            encontrados.add(identificador)

        elif fila["requiere_revision"] != "0":
            raise ValueError(
                f"Revision pendiente: {identificador}"
            )

        if nivel not in NIVELES_VALIDOS:
            raise ValueError(
                f"Nivel desconocido: {nivel}"
            )

        if tipo not in TIPOS_VALIDOS:
            raise ValueError(
                f"Tipo desconocido: {tipo}"
            )

        amenaza = int(fila["amenaza"])

        if amenaza != int(nivel != "INFO"):
            raise ValueError(
                f"Nivel y amenaza inconsistentes: {identificador}"
            )

        serial = identificador.rsplit(":", 1)[1]

        if serial != fila["serial"]:
            raise ValueError(
                f"Serial inconsistente: {identificador}"
            )

        criterio = (
            "revision_watchdog_journalctl"
            if identificador in ANOMALIAS_VERIFICADAS
            else original["criterio"]
        )

        filas.append({
            "event_id": identificador,
            "serial": serial,
            "fuente": fila["fuente"],
            "repeticion": fila["repeticion"],
            "grupo": fila["grupo"],
            "amenaza": amenaza,
            "nivel": nivel,
            "tipo": tipo,
            "criterio": criterio,
        })

    if encontrados != ANOMALIAS_VERIFICADAS:
        raise ValueError(
            "No se encontraron ambas anomalias."
        )

    if len(filas) != 519 or identificadores != set(referencia):
        raise ValueError(
            "El conjunto de etiquetas no coincide."
        )

    niveles = Counter(f["nivel"] for f in filas)
    tipos = Counter(f["tipo"] for f in filas)

    for nivel, esperado in DISTRIBUCION_ESPERADA.items():
        if niveles[nivel] != esperado:
            raise ValueError(
                f"{nivel}: esperado={esperado}, "
                f"obtenido={niveles[nivel]}"
            )

    resumen = {
        "estado": "DEFINITIVO",
        "total": len(filas),
        "niveles": {
            nivel: niveles[nivel]
            for nivel in ("INFO", "BAJO", "MEDIO", "ALTO")
        },
        "tipos": dict(sorted(tipos.items())),
        "anomalias_revisadas": sorted(encontrados),
        "pendientes_revision": 0,
        "observaciones": [
            "BAJO no tiene ejemplos de referencia.",
            "E4b representa una modificacion simulada.",
            "E3b_ataque representa privilegios simulados.",
            "Las etiquetas no deben enviarse a los clasificadores.",
        ],
    }

    DATA.mkdir(parents=True, exist_ok=True)

    with SALIDA.open(
        "x", newline="", encoding="utf-8"
    ) as archivo:
        writer = csv.DictWriter(
            archivo,
            fieldnames=list(filas[0])
        )
        writer.writeheader()
        writer.writerows(filas)

    with RESUMEN.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            resumen,
            archivo,
            indent=2,
            ensure_ascii=False,
        )

    print("=" * 60)
    print("ETIQUETAS MULTICLASE DEFINITIVAS - A2")
    print("=" * 60)

    print("Total eventos:", len(filas))

    print("\nNIVELES")
    for nivel in ("INFO", "BAJO", "MEDIO", "ALTO"):
        print(f"{nivel}: {niveles[nivel]}")

    print("\nTIPOS")
    for tipo, cantidad in sorted(tipos.items()):
        print(f"{tipo}: {cantidad}")

    print("\nAnomalias operativas verificadas:", len(encontrados))
    print("Pendientes de revision: 0")

    print("\nArchivos:")
    print(SALIDA)
    print(RESUMEN)

    print("\nVALIDACION GENERAL: OK")


if __name__ == "__main__":
    main()

