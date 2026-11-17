
import csv
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/processed/dataset"

ENTRADA = DATA / "etiquetas.csv"
EVENTOS = DATA / "eventos_unificados.jsonl"

SALIDA = DATA / "etiquetas_multiclase_borrador.csv"
RESUMEN = DATA / "resumen_etiquetas_borrador.json"

# Criterios definidos antes de clasificar.
CRITERIOS = {
    "NORMAL": ("INFO", "actividad_normal"),
    "E1": ("INFO", "actividad_normal"),
    "E2": ("MEDIO", None),
    "E3a": ("INFO", "actividad_normal"),
    "E3b_control": ("INFO", "actividad_normal"),
    "E3b_ataque": ("MEDIO", "anomalia_privilegios"),
    "E4a": ("INFO", "actividad_normal"),
    "E4b": ("ALTO", "modificacion_configuracion"),
    "E5a": ("INFO", "actividad_normal"),
    "E5b": ("ALTO", "acceso_sensible"),
}


def cargar_eventos():
    resultado = {}

    with EVENTOS.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            evento = json.loads(linea)
            identificador = evento["event_id"]

            if identificador in resultado:
                raise ValueError(
                    f"Evento duplicado: {identificador}"
                )

            resultado[identificador] = evento

    return resultado


def obtener_procesos(registros):
    procesos = set()

    patron = re.compile(
        r'\bcomm="([^"]+)"|\bcomm=([^\s]+)'
    )

    for registro in registros:
        if not registro.startswith("type=SYSCALL"):
            continue

        encontrado = patron.search(registro)

        if encontrado:
            procesos.add(
                encontrado.group(1)
                or encontrado.group(2)
            )

    return procesos


def clasificar_e2(registros):
    procesos = obtener_procesos(registros)

    # Consultas / intentos relacionados con identidad
    # y autenticacion.
    if procesos & {"sudo", "su"}:
        return "autenticacion", False

    if any(
        registro.startswith(
            ("type=USER_AUTH", "type=USER_ERR")
        )
        for registro in registros
    ):
        return "autenticacion", False

    if "find" in procesos:
        return "reconocimiento", False

    # No inventar un subtipo si falta evidencia.
    return "otro", True


def requiere_revision_normal(registros):
    tipos = set()

    for registro in registros:
        coincidencia = re.match(
            r"type=([A-Z_]+)", registro
        )
        if coincidencia:
            tipos.add(coincidencia.group(1))

    # Anomalias de terminacion de procesos.
    return "ANOM_ABEND" in tipos


def main():
    if SALIDA.exists() or RESUMEN.exists():
        raise SystemExit(
            "ERROR: ya existen archivos de salida. "
            "No se sobrescribiran."
        )

    eventos = cargar_eventos()
    filas = []

    with ENTRADA.open(
        newline="", encoding="utf-8"
    ) as archivo:
        etiquetas = list(csv.DictReader(archivo))

    if len(etiquetas) != 519:
        raise ValueError(
            "Cantidad inesperada de etiquetas."
        )

    for original in etiquetas:
        identificador = original["event_id"]
        fuente = original["fuente"]

        if identificador not in eventos:
            raise ValueError(
                f"No existe evento {identificador}"
            )

        if fuente not in CRITERIOS:
            raise ValueError(
                f"Fuente desconocida: {fuente}"
            )

        nivel, tipo = CRITERIOS[fuente]
        registros = eventos[identificador]["records"]
        revision = False
        motivo_revision = ""

        if fuente == "E2":
            tipo, revision = clasificar_e2(registros)

            if revision:
                motivo_revision = (
                    "No se pudo identificar el "
                    "subtipo de E2."
                )

        if fuente == "NORMAL":
            if requiere_revision_normal(registros):
                revision = True
                motivo_revision = (
                    "Terminacion anomala ANOM_ABEND. "
                    "Revisar contexto antes de "
                    "confirmar INFO."
                )

        serial = identificador.rsplit(":", 1)[1]

        amenaza = int(original["amenaza"])

        amenaza_esperada = int(
            nivel != "INFO"
        )

        if amenaza != amenaza_esperada:
            raise ValueError(
                f"Inconsistencia binaria: {identificador}"
            )

        filas.append({
            "event_id": identificador,
            "serial": serial,
            "fuente": fuente,
            "repeticion": original["repeticion"],
            "grupo": original["grupo"],
            "amenaza": amenaza,
            "nivel_propuesto": nivel,
            "tipo_propuesto": tipo,
            "requiere_revision": int(revision),
            "motivo_revision": motivo_revision,
        })

    if len(filas) != 519:
        raise ValueError(
            "No se generaron 519 etiquetas."
        )

    niveles = Counter(
        fila["nivel_propuesto"]
        for fila in filas
    )

    tipos = Counter(
        fila["tipo_propuesto"]
        for fila in filas
    )

    pendientes = [
        {
            "event_id": fila["event_id"],
            "fuente": fila["fuente"],
            "motivo": fila["motivo_revision"],
        }
        for fila in filas
        if fila["requiere_revision"]
    ]

    resumen = {
        "estado": "BORRADOR_NO_VALIDADO",
        "total": len(filas),
        "niveles_propuestos": dict(niveles),
        "tipos_propuestos": dict(tipos),
        "pendientes_revision": pendientes,
        "cantidad_pendientes": len(pendientes),
    }

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
    print("ETIQUETADO MULTICLASE - BORRADOR A2")
    print("=" * 60)

    print("Eventos:", len(filas))

    print("\nNIVELES PROPUESTOS")
    for nivel in ("INFO", "BAJO", "MEDIO", "ALTO"):
        print(
            f"{nivel}: {niveles[nivel]}"
        )

    print("\nTIPOS PROPUESTOS")
    for tipo, cantidad in sorted(tipos.items()):
        print(f"{tipo}: {cantidad}")

    print("\nEVENTOS PENDIENTES DE REVISION")
    print("Total:", len(pendientes))

    for pendiente in pendientes:
        print(
            pendiente["event_id"],
            pendiente["fuente"],
            pendiente["motivo"]
        )

    print("\nArchivos generados:")
    print(SALIDA)
    print(RESUMEN)

    print("\nBORRADOR GENERADO: OK")
    print("Las etiquetas aun no son definitivas.")


if __name__ == "__main__":
    main()

