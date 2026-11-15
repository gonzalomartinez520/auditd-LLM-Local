
import csv
import json
import pwd
import re
import shlex
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/raw/escenarios"

CSV_FILE = DATA / "e3a_ejecuciones.csv"
RAW_FILE = DATA / "e3a_ventana_completa_raw.log"
OUTPUT_FILE = DATA / "e3a_eventos_correlacionados.jsonl"

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

            eventos.setdefault(event_id, {
                "timestamp": float(match.group(1)),
                "records": [],
            })

            eventos[event_id]["records"].append(
                linea.rstrip("\n")
            )

    return eventos


def obtener_argumentos(records):
    for registro in records:
        if not registro.startswith("type=EXECVE"):
            continue

        argumentos = {}

        for match in re.finditer(
            r'\ba(\d+)="([^"]*)"', registro
        ):
            argumentos[int(match.group(1))] = match.group(2)

        return [
            argumentos[indice]
            for indice in sorted(argumentos)
        ]

    return []


def obtener_syscall(records):
    for registro in records:
        if registro.startswith("type=SYSCALL"):
            return registro

    return None


def main():
    if OUTPUT_FILE.exists():
        raise SystemExit(
            f"ERROR: ya existe {OUTPUT_FILE}"
        )

    with CSV_FILE.open(
        encoding="utf-8", newline=""
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

    for rep in repeticiones:
        numero = int(rep["repeticion"])

        inicio = datetime.fromisoformat(
            rep["inicio_utc"]
        ).timestamp()

        fin = datetime.fromisoformat(
            rep["fin_utc"]
        ).timestamp()

        comando_esperado = shlex.split(rep["comando"])

        # Formato:
        # sudo -n /usr/bin/apt-get update ...
        if (
            len(comando_esperado) < 4
            or comando_esperado[:2] != ["sudo", "-n"]
        ):
            problemas.append((numero, "comando_csv_invalido"))
            continue

        programa = Path(comando_esperado[2]).name
        usuario = rep["usuario_ejecutor"]
        uid = str(pwd.getpwnam(usuario).pw_uid)

        sudo_ids = set()
        apt_ids = set()

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
                and campo(syscall, "auid") == uid
            ):
                continue

            argumentos = obtener_argumentos(
                evento["records"]
            )

            comm = campo(syscall, "comm")
            exe = campo(syscall, "exe")

            # Comparar argumentos reales, no solamente
            # el nombre del proceso.
            if (
                comm == "sudo"
                and exe == "/usr/bin/sudo"
                and argumentos == comando_esperado
            ):
                sudo_ids.add(event_id)

            # La ejecución final se realiza como root.
            if (
                comm == programa
                and exe == comando_esperado[2]
                and campo(syscall, "uid") == "0"
                and argumentos == comando_esperado[2:]
            ):
                apt_ids.add(event_id)

        correcto = len(sudo_ids) == 1 and len(apt_ids) == 1

        print(
            f"E3a-{numero}: sudo={len(sudo_ids)}, "
            f"{programa}={len(apt_ids)} | "
            f"{'OK' if correcto else 'REVISAR'}"
        )

        if not correcto:
            problemas.append((numero, "correlacion_incompleta"))
            continue

        for tipo, identificadores in (
            ("sudo", sudo_ids),
            ("gestor_paquetes", apt_ids),
        ):
            for event_id in identificadores:
                if event_id in correlacionados:
                    problemas.append(
                        (numero, "evento_duplicado", event_id)
                    )
                    continue

                correlacionados[event_id] = {
                    "event_id": event_id,
                    "variante": "E3a",
                    "repeticion": numero,
                    "tipo_asociacion": tipo,
                    "usuario_ejecutor": usuario,
                    "records": eventos[event_id]["records"],
                }

                resumen[tipo] += 1

    print("\nRESUMEN")
    print("Repeticiones:", len(repeticiones))
    print("Ejecuciones sudo:", resumen["sudo"])
    print(
        "Ejecuciones apt/apt-get:",
        resumen["gestor_paquetes"]
    )
    print("Eventos correlacionados:", len(correlacionados))
    print("Problemas:", problemas)

    if problemas or len(correlacionados) != 20:
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

    print("\nCorrelacion E3a finalizada.")
    print("Archivo:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

