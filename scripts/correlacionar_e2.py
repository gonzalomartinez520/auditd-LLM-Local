
import csv
import json
import pwd
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/raw/escenarios"

CSV_FILE = DATA / "e2_ejecuciones.csv"
RAW_FILE = DATA / "e2_ventana_raw.log"
OUTPUT_FILE = DATA / "e2_eventos_correlacionados.jsonl"

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

            if event_id not in eventos:
                eventos[event_id] = {
                    "event_id": event_id,
                    "timestamp": float(match.group(1)),
                    "records": [],
                }

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
        acciones = list(csv.DictReader(archivo))

    eventos = cargar_eventos()
    correlacionados = {}
    problemas = []
    resumen = Counter()

    for fila in acciones:
        accion = fila["accion"]
        repeticion = int(fila["repeticion"])
        usuario = fila["usuario_ejecutor"]
        uid = str(pwd.getpwnam(usuario).pw_uid)

        inicio = datetime.fromisoformat(
            fila["inicio_utc"]
        ).timestamp()

        fin = datetime.fromisoformat(
            fila["fin_utc"]
        ).timestamp()

        candidatos = {
            event_id: evento
            for event_id, evento in eventos.items()
            if inicio - 0.5 <= evento["timestamp"] <= fin + 0.5
        }

        ejecuciones = []

        for event_id, evento in candidatos.items():
            for registro in evento["records"]:
                if (
                    registro.startswith("type=SYSCALL")
                    and campo(registro, "comm") == accion
                    and campo(registro, "uid") == uid
                    and campo(registro, "syscall") == "59"
                    and campo(registro, "success") == "yes"
                ):
                    ejecuciones.append(
                        (event_id, campo(registro, "pid"))
                    )

        ejecuciones = list(dict.fromkeys(ejecuciones))
        autenticaciones = []

        tipo_pam = {
            "sudo": "type=USER_ERR",
            "su": "type=USER_AUTH",
        }.get(accion)

        if tipo_pam:
            for exec_id, pid in ejecuciones:
                for event_id, evento in candidatos.items():
                    for registro in evento["records"]:
                        if (
                            registro.startswith(tipo_pam)
                            and campo(registro, "pid") == pid
                            and campo(registro, "uid") == uid
                            and campo(registro, "exe")
                                == f"/usr/bin/{accion}"
                            and campo(registro, "res") == "failed"
                        ):
                            autenticaciones.append(event_id)

        exec_ids = {x[0] for x in ejecuciones}
        auth_ids = set(autenticaciones)

        correcto = (
            len(exec_ids) == 1
            and (
                accion == "find"
                and len(auth_ids) == 0
                or accion in ("sudo", "su")
                and len(auth_ids) == 1
            )
        )

        if not correcto:
            problemas.append((repeticion, accion))
            continue

        for tipo, identificadores in [
            ("ejecucion", exec_ids),
            ("autenticacion_fallida", auth_ids),
        ]:
            for event_id in identificadores:
                if event_id in correlacionados:
                    problemas.append(
                        (repeticion, accion, "evento_repetido")
                    )
                    continue

                correlacionados[event_id] = {
                    "event_id": event_id,
                    "variante": "E2",
                    "repeticion": repeticion,
                    "accion": accion,
                    "usuario_ejecutor": usuario,
                    "tipo_asociacion": tipo,
                    "records": eventos[event_id]["records"],
                }

                resumen[tipo] += 1

    if problemas or len(correlacionados) != 50:
        print("Problemas:", problemas)
        print("Eventos encontrados:", len(correlacionados))
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
                int(e["event_id"].split(":")[1])
            ),
        ):
            archivo.write(
                json.dumps(
                    evento, ensure_ascii=False
                ) + "\n"
            )

    print("Correlacion E2 finalizada.")
    print("Acciones del CSV:", len(acciones))
    print("Eventos correlacionados:", len(correlacionados))
    print("Ejecuciones:", resumen["ejecucion"])
    print(
        "Autenticaciones fallidas:",
        resumen["autenticacion_fallida"]
    )
    print("Problemas:", problemas)
    print("Archivo:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

