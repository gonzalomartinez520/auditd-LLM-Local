
import csv
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUTPUT = BASE / "data/raw/escenarios/e3b_ejecuciones.csv"

SERVICIOS = ["www-data", "daemon", "nobody"]
SHELLS = ["/usr/bin/bash", "/usr/bin/sh"]
PAUSAS = [2, 3, 1, 4, 2, 3, 1, 4, 2]


def ahora():
    return datetime.now(timezone.utc).isoformat()


def ejecutar(comando):
    inicio = ahora()

    resultado = subprocess.run(
        comando,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    fin = ahora()

    return inicio, fin, resultado


def main():
    if os.geteuid() == 0:
        sys.exit("Ejecutar como usuario normal.")

    if OUTPUT.exists():
        sys.exit(f"El archivo ya existe: {OUTPUT}")

    if subprocess.run(
        ["sudo", "-n", "true"],
        capture_output=True,
    ).returncode != 0:
        sys.exit("Primero renovar la autenticacion sudo.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    columnas = [
        "repeticion", "variante", "tipo_prueba",
        "usuario_contexto", "comando",
        "inicio_utc", "fin_utc",
        "exit_code", "uid_observado",
        "uid_esperado", "resultado_esperado",
        "naturaleza",
    ]

    with OUTPUT.open("x", newline="", encoding="utf-8") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=columnas)
        writer.writeheader()

        for n in range(1, 11):
            usuario = SERVICIOS[(n - 1) % len(SERVICIOS)]
            shell = SHELLS[(n - 1) % len(SHELLS)]

            # Solo comprueba la identidad y termina.
            consulta = "/usr/bin/id -u"

            pruebas = [
                (
                    "servicio",
                    ["sudo", "-n", "runuser", "-u", usuario,
                     "--", shell, "-c", consulta],
                    str({
                        "www-data": 33,
                        "daemon": 1,
                        "nobody": 65534,
                    }[usuario]),
                ),
                (
                    "root_controlado",
                    ["sudo", "-n", shell, "-c", consulta],
                    "0",
                ),
            ]

            print(f"\nE3b - repeticion {n}/10", flush=True)

            for tipo, comando, esperado in pruebas:
                inicio, fin, resultado = ejecutar(comando)
                observado = resultado.stdout.strip()

                correcto = (
                    resultado.returncode == 0
                    and observado == esperado
                )

                writer.writerow({
                    "repeticion": n,
                    "variante": "E3b",
                    "tipo_prueba": tipo,
                    "usuario_contexto": usuario,
                    "comando": shlex.join(comando),
                    "inicio_utc": inicio,
                    "fin_utc": fin,
                    "exit_code": resultado.returncode,
                    "uid_observado": observado,
                    "uid_esperado": esperado,
                    "resultado_esperado": int(correcto),
                    "naturaleza": "simulacion_comparativa",
                })

                archivo.flush()

                print(
                    f"  {tipo}: uid={observado} "
                    f"| esperado={esperado} "
                    f"| correcto={correcto}",
                    flush=True,
                )

                if not correcto:
                    sys.exit(
                        "Resultado inesperado. "
                        "Revisar el CSV antes de continuar."
                    )

            if n < 10:
                time.sleep(PAUSAS[n - 1])

    print("\nSimulacion E3b finalizada.")
    print("Repeticiones:", 10)
    print("Ejecuciones:", 20)
    print("Archivo:", OUTPUT)


if __name__ == "__main__":
    main()

