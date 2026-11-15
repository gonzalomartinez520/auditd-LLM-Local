
import csv
import os
import pwd
import shlex
import shutil
import subprocess
import sys
import time

from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

OUTPUT_DIR = BASE_DIR / "data/raw/escenarios"
OUTPUT_FILE = OUTPUT_DIR / "e1_ejecuciones.csv"

# Distintas pausas entre repeticiones.
PAUSAS = [2, 3, 1, 4, 2, 3, 1, 2, 4]

# Las rutas alternativas apuntan al mismo archivo.
ESCENARIOS = [
    {
        "usuario": "actual",
        "comando": ["getent", "passwd", "root"],
        "consultado": "root",
    },
    {
        "usuario": "nobody",
        "comando": ["id", "root"],
        "consultado": "root",
    },
    {
        "usuario": "root",
        "comando": ["ls", "-l", "/etc/passwd"],
        "consultado": "",
    },
    {
        "usuario": "daemon",
        "comando": ["getent", "passwd", "nobody"],
        "consultado": "nobody",
    },
    {
        "usuario": "actual",
        "comando": ["id", "daemon"],
        "consultado": "daemon",
    },
    {
        "usuario": "nobody",
        "comando": ["ls", "-l", "/etc/./passwd"],
        "consultado": "",
    },
    {
        "usuario": "root",
        "comando": ["getent", "passwd", "daemon"],
        "consultado": "daemon",
    },
    {
        "usuario": "daemon",
        "comando": ["id", "nobody"],
        "consultado": "nobody",
    },
    {
        "usuario": "actual",
        "comando": ["ls", "-l", "/etc/../etc/passwd"],
        "consultado": "",
    },
    {
        "usuario": "nobody",
        "comando": ["getent", "passwd", "root"],
        "consultado": "root",
    },
]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def verificar_entorno():
    if os.geteuid() != 0:
        sys.exit(
            "ERROR: ejecutar con sudo python3 "
            "scripts/generar_e1.py"
        )

    usuario_original = os.environ.get("SUDO_USER")

    if not usuario_original or usuario_original == "root":
        sys.exit(
            "ERROR: ejecutar desde una cuenta normal "
            "utilizando sudo."
        )

    if shutil.which("runuser") is None:
        sys.exit("ERROR: no se encontró runuser.")

    usuarios = {
        usuario_original,
        "root",
        "nobody",
        "daemon",
    }

    for usuario in usuarios:
        try:
            pwd.getpwnam(usuario)
        except KeyError:
            sys.exit(
                f"ERROR: el usuario {usuario} no existe."
            )

    if len(ESCENARIOS) != 10:
        sys.exit("ERROR: E1 requiere 10 repeticiones.")

    if OUTPUT_FILE.exists():
        sys.exit(
            f"ERROR: ya existe {OUTPUT_FILE}. "
            "No se sobrescriben capturas anteriores."
        )

    return usuario_original


def main():
    usuario_original = verificar_entorno()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    campos = [
        "repeticion",
        "variante",
        "usuario_ejecutor",
        "usuario_consultado",
        "comando",
        "ruta_objetivo",
        "inicio_utc",
        "fin_utc",
        "pid_lanzador",
        "exit_code",
        "amenaza",
        "nivel_esperado",
    ]

    errores = 0

    with OUTPUT_FILE.open(
        "x", newline="", encoding="utf-8"
    ) as archivo:

        writer = csv.DictWriter(
            archivo,
            fieldnames=campos,
        )

        writer.writeheader()

        for numero, escenario in enumerate(
            ESCENARIOS, start=1
        ):
            usuario = escenario["usuario"]

            if usuario == "actual":
                usuario = usuario_original

            comando = escenario["comando"]

            # runuser permite cambiar el usuario ejecutor.
            comando_completo = [
                "runuser",
                "-u",
                usuario,
                "--",
                *comando,
            ]

            inicio = utc_now()

            proceso = subprocess.Popen(
                comando_completo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )

            _, error = proceso.communicate()
            fin = utc_now()

            if proceso.returncode != 0:
                errores += 1

            writer.writerow({
                "repeticion": numero,
                "variante": "E1",
                "usuario_ejecutor": usuario,
                "usuario_consultado": escenario["consultado"],
                "comando": shlex.join(comando),
                "ruta_objetivo": "/etc/passwd",
                "inicio_utc": inicio,
                "fin_utc": fin,
                "pid_lanzador": proceso.pid,
                "exit_code": proceso.returncode,
                "amenaza": 0,
                "nivel_esperado": "INFO",
            })

            archivo.flush()

            print(
                f"[E1 {numero}/10] "
                f"usuario={usuario} | "
                f"comando={shlex.join(comando)} | "
                f"exit={proceso.returncode}"
            )

            if error and proceso.returncode != 0:
                print(f"  Error: {error.strip()}")

            if numero < len(ESCENARIOS):
                time.sleep(PAUSAS[numero - 1])

    # Devolver la propiedad del CSV al usuario normal.
    propietario = pwd.getpwnam(usuario_original)

    os.chown(
        OUTPUT_FILE,
        propietario.pw_uid,
        propietario.pw_gid,
    )

    print("\nGeneración E1 finalizada.")
    print(f"Archivo: {OUTPUT_FILE}")
    print(f"Repeticiones: {len(ESCENARIOS)}")
    print(f"Errores: {errores}")

    if errores:
        sys.exit(
            "ATENCIÓN: revisar las repeticiones "
            "con exit_code distinto de cero."
        )


if __name__ == "__main__":
    main()

