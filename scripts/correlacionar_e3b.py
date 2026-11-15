
import csv
import json
import re
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/raw/escenarios"

CSV_FILE = DATA / "e3b_ejecuciones.csv"
RAW_FILE = DATA / "e3b_ventana_raw.log"
OUTPUT_FILE = DATA / "e3b_controles_correlacionados.jsonl"

AUDIT_PATTERN = re.compile(
    r"msg=audit\((\d+(?:\.\d+)?):(\d+)\)"
)


def campo(texto, nombre):
    match = re.search(
        rf'\b{re.escape(nombre)}=(?:"([^"]*)"|([^\s\x1d]+))',
        texto,
    )
    if not match:
        return None

    valor = match.group(1)
    if valor is None:
        valor = match.group(2)

    return valor.strip("'\"")


def cargar_eventos():
    eventos = {}

    with RAW_FILE.open(
        encoding="utf-8", errors="replace"
    ) as archivo:
        for linea in archivo:
            match = AUDIT_PATTERN.search(linea)
            if not match:
                continue

            event_id = f"{match.group(1)}:{match.group(2)}"

            eventos.setdefault(event_id, {
                "timestamp": float(match.group(1)),
                "records": [],
            })

            eventos[event_id]["records"].append(
                linea.rstrip("\n")
            )

    return eventos


def main():
    if OUTPUT_FILE.exists():
        raise SystemExit(
            f"ERROR: ya existe {OUTPUT_FILE}"
        )

    with CSV_FILE.open(
        newline="", encoding="utf-8"
    ) as archivo:
        ejecuciones = list(csv.DictReader(archivo))

    if len(ejecuciones) != 20:
        raise SystemExit(
            "ERROR: se esperaban 20 ejecuciones."
        )

    eventos = cargar_eventos()
    correlacionados = {}
    problemas = []

    for fila in ejecuciones:
        repeticion = int(fila["repeticion"])
        tipo = fila["tipo_prueba"]
        uid = fila["uid_esperado"]

        inicio = datetime.fromisoformat(
            fila["inicio_utc"]
        ).timestamp()

        fin = datetime.fromisoformat(
            fila["fin_utc"]
        ).timestamp()

        shells = set()
        ids = set()

        for event_id, evento in eventos.items():
            if not (
                inicio - 0.5
                <= evento["timestamp"]
                <= fin + 0.5
            ):
                continue

            for registro in evento["records"]:
                if not registro.startswith("type=SYSCALL"):
                    continue

                if not (
                    campo(registro, "syscall") == "59"
                    and campo(registro, "success") == "yes"
                    and campo(registro, "uid") == uid
                    and campo(registro, "euid") == uid
                ):
                    continue

                comm = campo(registro, "comm")
                exe = campo(registro, "exe")

                if (
                    comm in ("bash", "sh")
                    and exe in (
                        "/usr/bin/bash",
                        "/usr/bin/dash",
                    )
                ):
                    shells.add(event_id)

                if comm == "id" and exe == "/usr/bin/id":
                    ids.add(event_id)

        correcto = len(shells) == 1 and len(ids) == 1

        print(
            f"E3b-{repeticion} ({tipo}): "
            f"shell={len(shells)}, "
            f"id={len(ids)} | "
            f"{'OK' if correcto else 'REVISAR'}"
        )

        if not correcto:
            problemas.append((repeticion, tipo))
            continue

        for clase, identificadores in (
            ("shell", shells),
            ("id", ids),
        ):
            for event_id in identificadores:
                if event_id in correlacionados:
                    problemas.append(
                        (repeticion, tipo, "duplicado")
                    )
                    continue

                correlacionados[event_id] = {
                    "event_id": event_id,
                    "variante_original": "E3b",
                    "repeticion": repeticion,
                    "tipo_prueba": tipo,
                    "clase_evento": clase,
                    "uid_esperado": uid,
                    "naturaleza": "control_comparativo",
                    "amenaza": 0,
                    "records": eventos[event_id]["records"],
                }

    print("\nRESUMEN")
    print("Ejecuciones:", len(ejecuciones))
    print("Eventos correlacionados:", len(correlacionados))
    print("Problemas:", problemas)

    if problemas or len(correlacionados) != 40:
        raise SystemExit(
            "ERROR: correlacion incompleta. "
            "No se genero el archivo."
        )

    with OUTPUT_FILE.open(
        "x", encoding="utf-8"
    ) as archivo:
        for evento in sorted(
            correlacionados.values(),
            key=lambda e: (
                float(e["event_id"].split(":")[0]),
                int(e["event_id"].split(":")[1]),
            ),
        ):
            archivo.write(
                json.dumps(evento, ensure_ascii=False)
                + "\n"
            )

    print("Archivo generado:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

