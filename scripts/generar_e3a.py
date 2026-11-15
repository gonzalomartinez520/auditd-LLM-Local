
import csv
import os
import shlex
import shutil
import subprocess
import sys
import time

from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data/raw/escenarios"
OUTPUT_FILE = OUTPUT_DIR / "e3a_ejecuciones.csv"

PAUSAS = [2, 3, 1, 4, 2, 3, 2, 1, 4]

# Todas las variantes actualizan índices de paquetes.
COMANDOS = [
    ["/usr/bin/apt-get", "update"],
    ["/usr/bin/apt", "update"],
    ["/usr/bin/apt-get", "update", "-q"],
    ["/usr/bin/apt-get", "update", "-qq"],
    [
        "/usr/bin/apt-get", "update",
        "-o", "APT::Get::List-Cleanup=1"
    ],
    [
        "/usr/bin/apt-get", "update",
        "-o", "Acquire::Retries=0"
    ],
    ["/usr/bin/apt", "update", "-q"],
    [
        "/usr/bin/apt-get", "update",
        "-o", "Acquire::Languages=none"
    ],
    [
        "/usr/bin/apt-get", "update",
        "-q", "-o", "Acquire::Retries=0"
    ],
    ["/usr/bin/apt-get", "update"],
]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def verificar_entorno():
    if os.geteuid() == 0:
        sys.exit(
            "ERROR: ejecutar como usuario normal, "
            "no mediante sudo python3."
        )

    for programa in ("/usr/bin/apt", "/usr/bin/apt-get"):
        if not Path(programa).is_file():
            sys.exit(f"ERROR: falta {programa}")

    if shutil.which("sudo") is None:
        sys.exit("ERROR: sudo no disponible")

    if len(COMANDOS) != 10:
        sys.exit("ERROR: deben existir 10 repeticiones")

    if OUTPUT_FILE.exists():
        sys.exit(
            f"ERROR: ya existe {OUTPUT_FILE}. "
            "No se sobrescriben capturas."
        )

    resultado = subprocess.run(
        ["sudo", "-n", "true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    if resultado.returncode != 0:
        sys.exit(
            "ERROR: sudo -n no está autorizado. "
            "Verificar antes de continuar."
        )


def main():
    verificar_entorno()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    campos = [
        "repeticion",
        "variante",
        "usuario_ejecutor",
        "comando",
        "inicio_utc",
        "fin_utc",
        "duracion_segundos",
        "exit_code",
        "amenaza",
        "nivel_esperado",
    ]

    usuario = os.environ.get("USER", str(os.getuid()))
    completadas = 0

    with OUTPUT_FILE.open(
        "x", newline="", encoding="utf-8"
    ) as archivo:

        writer = csv.DictWriter(
            archivo, fieldnames=campos
        )
        writer.writeheader()

        for numero, comando in enumerate(COMANDOS, 1):
            comando_completo = [
                "sudo", "-n", *comando
            ]

            print(
                f"\nE3a - repeticion {numero}/10: "
                f"{shlex.join(comando_completo)}",
                flush=True,
            )

            inicio = utc_now()
            inicio_medicion = time.monotonic()

            try:
                resultado = subprocess.run(
                    comando_completo,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=180,
                    check=False,
                )

                codigo = resultado.returncode
                error = resultado.stderr.strip()

            except subprocess.TimeoutExpired:
                print(
                    "ERROR: tiempo limite excedido. "
                    "Revisar procesos apt antes de continuar."
                )
                break

            fin = utc_now()
            duracion = round(
                time.monotonic() - inicio_medicion, 3
            )

            writer.writerow({
                "repeticion": numero,
                "variante": "E3a",
                "usuario_ejecutor": usuario,
                "comando": shlex.join(comando_completo),
                "inicio_utc": inicio,
                "fin_utc": fin,
                "duracion_segundos": duracion,
                "exit_code": codigo,
                "amenaza": 0,
                "nivel_esperado": "INFO",
            })

            archivo.flush()
            completadas += 1

            print(
                f"  exit={codigo} | "
                f"duracion={duracion}s",
                flush=True,
            )

            if codigo != 0:
                print(f"  Detalle: {error}")
                print(
                    "Ejecucion detenida para revisar "
                    "el error."
                )
                break

            if numero < len(COMANDOS):
                time.sleep(PAUSAS[numero - 1])

    print("\nResumen E3a:")
    print(f"Repeticiones registradas: {completadas}")
    print(f"Archivo: {OUTPUT_FILE}")

    if completadas != 10:
        sys.exit(
            "ATENCION: E3a incompleto. "
            "No volver a ejecutar sin revisar el CSV."
        )


if __name__ == "__main__":
    main()

