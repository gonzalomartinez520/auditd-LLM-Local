
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/raw/escenarios"

CSV_FILE = DATA / "e5a_ejecuciones.csv"
RAW_FILE = DATA / "e5a_ventana_raw.log"
OUTPUT_FILE = DATA / "e5a_eventos_correlacionados.jsonl"

ARCHIVOS_PERMITIDOS = {"/etc/passwd", "/etc/shadow"}

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
        encoding="utf-8", errors="replace"
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


def analizar_acceso(records, proceso):
    syscall = next(
        (
            registro
            for registro in records
            if registro.startswith("type=SYSCALL")
        ),
        None,
    )

    if syscall is None:
        return None

    if not (
        campo(syscall, "syscall") == "257"
        and campo(syscall, "success") == "yes"
        and campo(syscall, "comm") == proceso
        and campo(syscall, "exe") == f"/usr/bin/{proceso}"
        and campo(syscall, "euid") == "0"
        and campo(syscall, "key") == "a2_file_access"
    ):
        return None

    rutas = {
        campo(registro, "name")
        for registro in records
        if registro.startswith("type=PATH")
    }

    rutas_validas = rutas & ARCHIVOS_PERMITIDOS

    # Cada evento debe corresponder a un único archivo.
    if len(rutas_validas) != 1:
        return None

    return next(iter(rutas_validas))


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
    totales = Counter()

    for fila in repeticiones:
        numero = int(fila["repeticion"])
        tipo = fila["tipo_consulta"]

        if tipo == "passwd_estado":
            proceso = "passwd"
            esperado_passwd = 4
            esperado_shadow = 1
        elif tipo == "chage_caducidad":
            proceso = "chage"
            esperado_passwd = 1
            esperado_shadow = 1
        else:
            problemas.append((numero, "tipo_desconocido"))
            continue

        if (
            fila["exit_code"] != "0"
            or fila["resultado_esperado"] != "1"
        ):
            problemas.append((numero, "ejecucion_fallida"))
            continue

        inicio = datetime.fromisoformat(
            fila["inicio_utc"]
        ).timestamp()

        fin = datetime.fromisoformat(
            fila["fin_utc"]
        ).timestamp()

        candidatos = {}

        for event_id, evento in eventos.items():
            if not (
                inicio - 0.5
                <= evento["timestamp"]
                <= fin + 0.5
            ):
                continue

            ruta = analizar_acceso(
                evento["records"], proceso
            )

            if ruta is not None:
                candidatos[event_id] = ruta

        conteos = Counter(candidatos.values())

        correcto = (
            conteos["/etc/passwd"] == esperado_passwd
            and conteos["/etc/shadow"] == esperado_shadow
            and len(candidatos)
            == esperado_passwd + esperado_shadow
        )

        print(
            f'E5a-{numero} ({proceso}): '
            f'passwd={conteos["/etc/passwd"]}, '
            f'shadow={conteos["/etc/shadow"]}, '
            f'eventos={len(candidatos)} | '
            f'{"OK" if correcto else "REVISAR"}'
        )

        if not correcto:
            problemas.append(
                (numero, "cantidad_incorrecta")
            )
            continue

        for event_id, ruta in candidatos.items():
            if event_id in correlacionados:
                problemas.append(
                    (numero, "duplicado", event_id)
                )
                continue

            correlacionados[event_id] = {
                "event_id": event_id,
                "variante": "E5a",
                "repeticion": numero,
                "tipo_consulta": tipo,
                "usuario_consultado": fila[
                    "usuario_consultado"
                ],
                "proceso": proceso,
                "archivo_accedido": ruta,
                "operacion": "lectura_legitima",
                "naturaleza": "consulta_administrativa",
                "amenaza": 0,
                "nivel": "INFO",
                "records": eventos[event_id]["records"],
            }

            totales[ruta] += 1

    print("\nRESUMEN")
    print("Repeticiones:", len(repeticiones))
    print("Lecturas /etc/passwd:", totales["/etc/passwd"])
    print("Lecturas /etc/shadow:", totales["/etc/shadow"])
    print("Eventos correlacionados:", len(correlacionados))
    print("Problemas:", problemas)

    if (
        problemas
        or len(correlacionados) != 35
        or totales["/etc/passwd"] != 25
        or totales["/etc/shadow"] != 10
    ):
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

    print("\nCorrelacion E5a finalizada.")
    print("Archivo:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

