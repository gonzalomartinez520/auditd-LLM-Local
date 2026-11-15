
import csv
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUTPUT = BASE / "data/raw/escenarios/e3b_ataque_ejecuciones.csv"

USUARIOS = [
    ("www-data", 33),
    ("daemon", 1),
    ("nobody", 65534),
]

PAUSAS = [2, 3, 1, 4, 2, 3, 1, 2, 4]


def ahora():
    return datetime.now(timezone.utc).isoformat()


def main():
    if os.geteuid() == 0:
        sys.exit("Ejecutar como usuario normal, no con sudo.")

    if OUTPUT.exists():
        sys.exit(f"ERROR: ya existe {OUTPUT}")

    # Autenticacion previa, fuera de las repeticiones.
    verificacion = subprocess.run(
        ["sudo", "-n", "true"],
        capture_output=True,
        text=True,
        check=False,
    )

    if verificacion.returncode != 0:
        sys.exit("ERROR: ejecutar primero sudo -v.")

    columnas = [
        "repeticion",
        "variante",
        "usuario_contexto",
        "uid_real_esperado",
        "euid_esperado",
        "comando",
        "inicio_utc",
        "fin_utc",
        "exit_code",
        "uid_real_observado",
        "euid_observado",
        "resultado_esperado",
        "naturaleza",
        "amenaza",
        "nivel",
    ]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open(
        "x", newline="", encoding="utf-8"
    ) as archivo:

        writer = csv.DictWriter(
            archivo, fieldnames=columnas
        )
        writer.writeheader()
        archivo.flush()

        for n in range(1, 11):
            usuario, uid = USUARIOS[
                (n - 1) % len(USUARIOS)
            ]

            # Diferentes formas de consultar credenciales.
            if n % 2 == 0:
                consulta = (
                    "/usr/bin/id -ru; "
                    "/usr/bin/id -u; "
                    "/usr/bin/id"
                )
            else:
                consulta = (
                    "/usr/bin/id; "
                    "/usr/bin/id -ru; "
                    "/usr/bin/id -u"
                )

            comando = [
                "sudo", "-n",
                "/usr/bin/setpriv",
                "--ruid", str(uid),
                "--euid", "0",
                "--rgid", str(uid),
                "--egid", "0",
                "--groups", str(uid),
                "/usr/bin/bash", "-p", "-c", consulta,
            ]

            print(
                f"\nE3b ataque - repeticion {n}/10 "
                f"({usuario})",
                flush=True,
            )

            inicio = ahora()

            try:
                resultado = subprocess.run(
                    comando,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                sys.exit(
                    f"ERROR: timeout en repeticion {n}"
                )

            fin = ahora()

            lineas = resultado.stdout.strip().splitlines()

            # Identificar las salidas de id -ru e id -u
            # sin depender de su orden.
            valores = [
                linea.strip()
                for linea in lineas
                if linea.strip().isdigit()
            ]

            correcto = (
                resultado.returncode == 0
                and valores == [str(uid), "0"]
                and f"uid={uid}(" in resultado.stdout
                and "euid=0(root)" in resultado.stdout
            )

            writer.writerow({
                "repeticion": n,
                "variante": "E3b",
                "usuario_contexto": usuario,
                "uid_real_esperado": uid,
                "euid_esperado": 0,
                "comando": shlex.join(comando),
                "inicio_utc": inicio,
                "fin_utc": fin,
                "exit_code": resultado.returncode,
                "uid_real_observado": (
                    valores[0] if len(valores) > 0 else ""
                ),
                "euid_observado": (
                    valores[1] if len(valores) > 1 else ""
                ),
                "resultado_esperado": int(correcto),
                "naturaleza": "simulacion_sintetica",
                "amenaza": 1,
                "nivel": "ALTO",
            })

            archivo.flush()

            print(
                f"  UID real: "
                f"{valores[0] if valores else 'NO DETECTADO'}"
            )
            print(
                f"  EUID: "
                f"{valores[1] if len(valores) > 1 else 'NO DETECTADO'}"
            )
            print(f"  Exit code: {resultado.returncode}")
            print(f"  Correcto: {correcto}", flush=True)

            if not correcto:
                print(resultado.stderr)
                sys.exit(
                    "Resultado inesperado. "
                    "Revisar antes de continuar."
                )

            if n < 10:
                time.sleep(PAUSAS[n - 1])

    print("\nSimulacion E3b finalizada.")
    print("Repeticiones correctas: 10")
    print("Archivo:", OUTPUT)


if __name__ == "__main__":
    main()

