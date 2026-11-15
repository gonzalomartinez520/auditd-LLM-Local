
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUTPUT = BASE / "data/raw/escenarios/e4a_ejecuciones.csv"

ARCHIVO = "/etc/sudoers.d/a2_e4a_prueba"
PAUSAS = [2, 1, 3, 2, 1, 3, 2, 1, 3]


def ahora():
    return datetime.now(timezone.utc).isoformat()


def ejecutar(comando, entrada=None):
    return subprocess.run(
        comando,
        input=entrada,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


def verificar_archivo():
    estado = ejecutar([
        "sudo", "-n", "stat", "-c", "%u:%g:%a",
        ARCHIVO,
    ])

    if estado.returncode != 0:
        sys.exit("ERROR: no se pudo verificar el archivo.")

    if estado.stdout.strip() != "0:0:440":
        sys.exit(
            "ERROR: propietario o permisos inesperados: "
            + estado.stdout.strip()
        )

    contenido = ejecutar([
        "sudo", "-n", "cat", ARCHIVO,
    ])

    if contenido.returncode != 0:
        sys.exit("ERROR: no se pudo leer el archivo.")

    for linea in contenido.stdout.splitlines():
        if linea.strip() and not linea.lstrip().startswith("#"):
            sys.exit(
                "ERROR: el archivo contiene una directiva "
                "que no es un comentario."
            )


def validar_sudo():
    archivo = ejecutar([
        "sudo", "-n", "visudo", "-cf", ARCHIVO,
    ])

    global_ = ejecutar([
        "sudo", "-n", "visudo", "-c",
    ])

    return (
        archivo.returncode == 0
        and global_.returncode == 0
    )


def main():
    if os.geteuid() == 0:
        sys.exit("Ejecutar como usuario normal.")

    if OUTPUT.exists():
        sys.exit(f"ERROR: el CSV ya existe: {OUTPUT}")

    autenticacion = ejecutar(["sudo", "-n", "true"])

    if autenticacion.returncode != 0:
        sys.exit("ERROR: ejecutar sudo -v primero.")

    verificar_archivo()

    if not validar_sudo():
        sys.exit("ERROR: configuracion sudo invalida.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    columnas = [
        "repeticion",
        "variante",
        "archivo",
        "operacion",
        "inicio_utc",
        "fin_utc",
        "exit_code",
        "validacion_ok",
        "resultado_esperado",
        "amenaza",
        "nivel",
    ]

    with OUTPUT.open(
        "x", newline="", encoding="utf-8"
    ) as archivo_csv:

        writer = csv.DictWriter(
            archivo_csv,
            fieldnames=columnas
        )
        writer.writeheader()
        archivo_csv.flush()

        for n in range(1, 11):
            verificar_archivo()

            contenido = (
                "# A2 - Escenario E4a\n"
                "# Mantenimiento autorizado de configuracion\n"
                f"# Revision experimental numero {n}\n"
                f"# Control de auditoria: {n * 7}\n"
            )

            comando = [
                "sudo", "-n", "tee", ARCHIVO,
            ]

            inicio = ahora()
            escritura = ejecutar(
                comando, entrada=contenido
            )
            fin = ahora()

            validacion_ok = (
                escritura.returncode == 0
                and validar_sudo()
            )

            correcto = (
                escritura.returncode == 0
                and validacion_ok
            )

            writer.writerow({
                "repeticion": n,
                "variante": "E4a",
                "archivo": ARCHIVO,
                "operacion": "escritura_autorizada",
                "inicio_utc": inicio,
                "fin_utc": fin,
                "exit_code": escritura.returncode,
                "validacion_ok": int(validacion_ok),
                "resultado_esperado": int(correcto),
                "amenaza": 0,
                "nivel": "INFO",
            })

            archivo_csv.flush()

            print(
                f"E4a-{n}: escritura={escritura.returncode}, "
                f"visudo={'OK' if validacion_ok else 'ERROR'} "
                f"| {'OK' if correcto else 'REVISAR'}",
                flush=True,
            )

            if not correcto:
                sys.exit(
                    "ERROR: detener experimento y revisar "
                    "la configuracion."
                )

            if n < 10:
                time.sleep(PAUSAS[n - 1])

    print("\nE4a finalizado.")
    print("Repeticiones:", 10)
    print("Archivo CSV:", OUTPUT)


if __name__ == "__main__":
    main()

