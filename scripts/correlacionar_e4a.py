
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/raw/escenarios"

CSV_FILE = DATA / "e4a_ejecuciones.csv"
RAW_FILE = DATA / "e4a_ventana_raw.log"
OUTPUT_FILE = DATA / "e4a_eventos_correlacionados.jsonl"

RUTA_OBJETIVO = "/etc/sudoers.d/a2_e4a_prueba"

AUDIT_PATTERN = re.compile(
    r"msg=audit\((\d+(?:\.\d+)?):(\d+)\)"
)


def campo(registro, nombre):
    match = re.search(
        rf'\b{re.escape(nombre)}=(?:"([^"]*)"|([^\s\x1d]+))',
        registro,
    )

    if not match:
        return None

    return (
        match.group(1)
        if match.group(1) is not None
        else match.group(2)
    )


def cargar_eventos():
    eventos = {}

    with RAW_FILE.open(
        encoding="utf-8",
        errors="replace",
    ) as archivo:
        for linea in archivo:
            match = AUDIT_PATTERN.search(linea)

            if not match:
                continue

            event_id = f"{match.group(1)}:{match.group(2)}"

            evento = eventos.setdefault(
                event_id,
                {
                    "timestamp": float(match.group(1)),
                    "records": [],
                },
            )

            evento["records"].append(
                linea.rstrip("\n")
            )

    return eventos


def escritura_valida(records):
    syscall = next(
        (
            registro
            for registro in records
            if registro.startswith("type=SYSCALL")
        ),
        None,
    )

    if syscall is None:
        return False

    condiciones = (
        campo(syscall, "syscall") == "257"
        and campo(syscall, "success") == "yes"
        and campo(syscall, "comm") == "tee"
        and campo(syscall, "exe") == "/usr/bin/tee"
        and campo(syscall, "uid") == "0"
        and campo(syscall, "euid") == "0"
        and campo(syscall, "key") == "a2_config_access"
    )

    if not condiciones:
        return False

    return any(
        registro.startswith("type=PATH")
        and campo(registro, "name") == RUTA_OBJETIVO
        for registro in records
    )


def main():
    if OUTPUT_FILE.exists():
        raise SystemExit(
            f"ERROR: ya existe {OUTPUT_FILE}"
        )

    with CSV_FILE.open(
        encoding="utf-8",
        newline="",
    ) as archivo:
        repeticiones = list(
            csv.DictReader(archivo)
        )

    if len(repeticiones) != 10:
        raise SystemExit(
            "ERROR: se esperaban 10 repeticiones."
        )

    eventos = cargar_eventos()
    correlacionados = {}
    problemas = []

    for fila in repeticiones:
        numero = int(fila["repeticion"])

        inicio = datetime.fromisoformat(
            fila["inicio_utc"]
        ).timestamp()

        fin = datetime.fromisoformat(
            fila["fin_utc"]
        ).timestamp()

        candidatos = []

        for event_id, evento in eventos.items():
            if not (
                inicio - 0.5
                <= evento["timestamp"]
                <= fin + 0.5
            ):
                continue

            if escritura_valida(
                evento["records"]
            ):
                candidatos.append(event_id)

        correcto = len(candidatos) == 1

        print(
            f"E4a-{numero}: "
            f"escrituras={len(candidatos)} | "
            f"{'OK' if correcto else 'REVISAR'}"
        )

        if not correcto:
            problemas.append(
                (numero, "cantidad_incorrecta")
            )
            continue

        event_id = candidatos[0]

        if event_id in correlacionados:
            problemas.append(
                (numero, "evento_duplicado", event_id)
            )
            continue

        correlacionados[event_id] = {
            "event_id": event_id,
            "variante": "E4a",
            "repeticion": numero,
            "archivo_objetivo": RUTA_OBJETIVO,
            "operacion": "escritura_autorizada",
            "naturaleza": "simulacion_legitima",
            "amenaza": 0,
            "nivel": "INFO",
            "records": eventos[event_id]["records"],
        }

    print("\nRESUMEN")
    print("Repeticiones:", len(repeticiones))
    print(
        "Eventos correlacionados:",
        len(correlacionados)
    )
    print("Problemas:", problemas)

    if problemas or len(correlacionados) != 10:
        raise SystemExit(
            "ERROR: correlacion incompleta. "
            "No se genero el archivo."
        )

    with OUTPUT_FILE.open(
        "x",
        encoding="utf-8",
    ) as archivo:
        for evento in sorted(
            correlacionados.values(),
            key=lambda e: (
                float(
                    e["event_id"].split(":")[0]
                ),
                int(
                    e["event_id"].split(":")[1]
                ),
            ),
        ):
            archivo.write(
                json.dumps(
                    evento,
                    ensure_ascii=False,
                ) + "\n"
            )

    print("\nCorrelacion E4a finalizada.")
    print("Archivo:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

