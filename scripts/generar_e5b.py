
import csv
import os
import shlex
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUTPUT = BASE / "data/raw/escenarios/e5b_ejecuciones.csv"

OBJETIVO = "/etc/shadow"
DESTINO = "/dev/null"

PAUSAS = [2, 3, 1, 4, 2, 3, 1, 2, 4]


def ahora():
    return datetime.now(timezone.utc).isoformat()


def verificar_entorno():
    if os.geteuid() == 0:
        sys.exit("ERROR: ejecutar como usuario normal.")

    if OUTPUT.exists():
        sys.exit(f"ERROR: el CSV ya existe: {OUTPUT}")

    estado = os.stat(DESTINO)

    if not (
        stat.S_ISCHR(estado.st_mode)
        and os.major(estado.st_rdev) == 1
        and os.minor(estado.st_rdev) == 3
    ):
        sys.exit("ERROR: /dev/null no es el dispositivo esperado.")

    if not Path(OBJETIVO).is_file():
        sys.exit("ERROR: falta /etc/shadow.")

    for programa in ("/usr/bin/cat", "/usr/bin/cp"):
        if not Path(programa).is_file():
            sys.exit(f"ERROR: falta {programa}")

    autenticacion = subprocess.run(
        ["sudo", "-n", "true"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    if autenticacion.returncode != 0:
        sys.exit("ERROR: ejecutar sudo -v primero.")


def main():
    verificar_entorno()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    columnas = [
        "repeticion",
        "variante",
        "tipo_acceso",
        "archivo_objetivo",
        "destino",
        "comando",
        "inicio_utc",
        "fin_utc",
        "exit_code",
        "resultado_esperado",
        "naturaleza",
        "amenaza",
        "nivel",
    ]

    with OUTPUT.open(
        "x", newline="", encoding="utf-8"
    ) as archivo:

        writer = csv.DictWriter(
            archivo, fieldnames=columnas
        )
        writer.writeheader()
        archivo.flush()

        for n in range(1, 11):
            # Cinco ejecuciones con cat y cinco con cp.
            if n % 2 == 1:
                tipo = "cat"
                comando = [
                    "sudo", "-n",
                    "/usr/bin/cat",
                    OBJETIVO,
                ]
            else:
                tipo = "cp"
                comando = [
                    "sudo", "-n",
                    "/usr/bin/cp",
                    OBJETIVO,
                    DESTINO,
                ]

            print(
                f"E5b-{n}: acceso mediante {tipo}",
                flush=True,
            )

            inicio = ahora()

            try:
                resultado = subprocess.run(
                    comando,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                sys.exit(
                    f"ERROR: timeout en E5b-{n}"
                )

            fin = ahora()
            correcto = resultado.returncode == 0

            writer.writerow({
                "repeticion": n,
                "variante": "E5b",
                "tipo_acceso": tipo,
                "archivo_objetivo": OBJETIVO,
                "destino": DESTINO,
                "comando": shlex.join(comando),
                "inicio_utc": inicio,
                "fin_utc": fin,
                "exit_code": resultado.returncode,
                "resultado_esperado": int(correcto),
                "naturaleza": "simulacion_sospechosa",
                "amenaza": 1,
                "nivel": "ALTO",
            })

            archivo.flush()

            print(
                f"  Exit code: {resultado.returncode}"
            )
            print(
                f"  Correcto: {correcto}",
                flush=True,
            )

            if not correcto:
                sys.exit(
                    "ERROR: ejecucion fallida. "
                    "Revisar antes de continuar."
                )

            if n < 10:
                time.sleep(PAUSAS[n - 1])

    print("\nE5b finalizado.")
    print("Repeticiones correctas: 10")
    print("Archivo CSV:", OUTPUT)


if __name__ == "__main__":
    main()

