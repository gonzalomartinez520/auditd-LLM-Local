
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/raw/escenarios"

CSV_FILE = DATA / "e3b_ataque_ejecuciones.csv"
RAW_FILE = DATA / "e3b_ataque_ventana_raw.log"
OUTPUT_FILE = DATA / "e3b_ataque_eventos_correlacionados.jsonl"

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


def obtener_syscall(records):
    for registro in records:
        if registro.startswith("type=SYSCALL"):
            return registro
    return None


def obtener_argumentos(records):
    for registro in records:
        if not registro.startswith("type=EXECVE"):
            continue

        argumentos = {}

        for match in re.finditer(
            r'\ba(\d+)=("[^"]*"|[^\s\x1d]+)',
            registro
        ):
            indice = int(match.group(1))
            valor = match.group(2)

            if valor.startswith('"') and valor.endswith('"'):
                valor = valor[1:-1]
            else:
                try:
                    valor = bytes.fromhex(valor).decode("utf-8")
                except (ValueError, UnicodeDecodeError):
                    pass

            argumentos[indice] = valor

        return [
            argumentos[i]
            for i in sorted(argumentos)
        ]

    return []


def main():
    if OUTPUT_FILE.exists():
        raise SystemExit(
            f"ERROR: ya existe {OUTPUT_FILE}"
        )

    with CSV_FILE.open(
        newline="", encoding="utf-8"
    ) as archivo:
        repeticiones = list(csv.DictReader(archivo))

    if len(repeticiones) != 10:
        raise SystemExit(
            "ERROR: se esperaban 10 repeticiones."
        )

    eventos = cargar_eventos()
    correlacionados = {}
    problemas = []
    resumen = Counter()

    for fila in repeticiones:
        numero = int(fila["repeticion"])
        uid = fila["uid_real_esperado"]
        euid = fila["euid_esperado"]

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

            syscall = obtener_syscall(evento["records"])

            if syscall is None:
                continue

            if not (
                campo(syscall, "syscall") == "59"
                and campo(syscall, "success") == "yes"
                and campo(syscall, "uid") == uid
                and campo(syscall, "euid") == euid
            ):
                continue

            comm = campo(syscall, "comm")
            exe = campo(syscall, "exe")
            argumentos = obtener_argumentos(
                evento["records"]
            )

            if (
                comm == "bash"
                and exe == "/usr/bin/bash"
                and len(argumentos) >= 4
                and argumentos[:3] == [
                    "/usr/bin/bash", "-p", "-c"
                ]
            ):
                shells.add(event_id)

            if (
                comm == "id"
                and exe == "/usr/bin/id"
                and argumentos
                and argumentos[0] == "/usr/bin/id"
            ):
                ids.add(event_id)

        correcto = len(shells) == 1 and len(ids) == 3

        print(
            f"E3b-{numero}: "
            f"bash={len(shells)}, "
            f"id={len(ids)} | "
            f"{'OK' if correcto else 'REVISAR'}"
        )

        if not correcto:
            problemas.append(numero)
            continue

        for clase, identificadores in (
            ("shell_privilegiada", shells),
            ("verificacion_identidad", ids),
        ):
            for event_id in identificadores:
                if event_id in correlacionados:
                    problemas.append(
                        (numero, "duplicado", event_id)
                    )
                    continue

                correlacionados[event_id] = {
                    "event_id": event_id,
                    "variante": "E3b",
                    "repeticion": numero,
                    "usuario_contexto": fila[
                        "usuario_contexto"
                    ],
                    "uid_real_esperado": uid,
                    "euid_esperado": euid,
                    "clase_evento": clase,
                    "naturaleza": "simulacion_sintetica",
                    "amenaza": 1,
                    "nivel": "ALTO",
                    "records": eventos[event_id]["records"],
                }

                resumen[clase] += 1

    print("\nRESUMEN")
    print("Repeticiones:", len(repeticiones))
    print(
        "Shells privilegiadas:",
        resumen["shell_privilegiada"]
    )
    print(
        "Verificaciones de identidad:",
        resumen["verificacion_identidad"]
    )
    print(
        "Eventos correlacionados:",
        len(correlacionados)
    )
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
                json.dumps(
                    evento, ensure_ascii=False
                ) + "\n"
            )

    print("\nCorrelacion E3b finalizada.")
    print("Archivo:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

