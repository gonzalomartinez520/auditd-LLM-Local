
import csv
import hashlib
import os
import pwd
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUTPUT = BASE / "data/raw/escenarios/e4b_ejecuciones.csv"

DIRECTORIO = "/var/tmp/a2-e4b-lab"
ARCHIVO = DIRECTORIO + "/politica_simulada"

PAUSAS = [2, 1, 3, 2, 4, 1, 3, 2, 1]


def ahora():
    return datetime.now(timezone.utc).isoformat()


def ejecutar(comando, entrada=None):
    return subprocess.run(
        comando,
        input=entrada,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def cuenta_inexistente(nombre):
    try:
        pwd.getpwnam(nombre)
    except KeyError:
        return True
    return False


def verificar_entorno():
    if os.geteuid() == 0:
        sys.exit("ERROR: ejecutar como usuario normal.")

    if OUTPUT.exists():
        sys.exit(f"ERROR: ya existe {OUTPUT}")

    if ejecutar(["sudo", "-n", "true"]).returncode != 0:
        sys.exit("ERROR: ejecutar sudo -v primero.")

    estado = ejecutar([
        "sudo", "-n", "stat", "-c", "%u:%g:%a",
        DIRECTORIO,
    ])

    if (
        estado.returncode != 0
        or estado.stdout.strip() != "0:0:700"
    ):
        sys.exit("ERROR: directorio de laboratorio inseguro.")

    if ejecutar([
        "sudo", "-n", "test", "-f", ARCHIVO
    ]).returncode != 0:
        sys.exit("ERROR: falta el archivo simulado.")

    if ejecutar([
        "sudo", "-n", "visudo", "-c"
    ]).returncode != 0:
        sys.exit("ERROR: configuracion real invalida.")

    if ejecutar([
        "sudo", "-n", "visudo", "-cf", ARCHIVO
    ]).returncode != 0:
        sys.exit("ERROR: configuracion simulada invalida.")


def main():
    verificar_entorno()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    columnas = [
        "repeticion",
        "variante",
        "archivo",
        "usuario_ficticio",
        "regla_simulada",
        "sha256_contenido",
        "inicio_utc",
        "fin_utc",
        "exit_code",
        "contenido_ok",
        "visudo_ok",
        "resultado_esperado",
        "naturaleza",
        "amenaza",
        "nivel",
    ]

    with OUTPUT.open(
        "x", newline="", encoding="utf-8"
    ) as archivo_csv:

        writer = csv.DictWriter(
            archivo_csv, fieldnames=columnas
        )
        writer.writeheader()
        archivo_csv.flush()

        for n in range(1, 11):
            usuario = f"a2_e4b_inexistente_{n:02d}"

            if not cuenta_inexistente(usuario):
                sys.exit(
                    f"ERROR: la cuenta {usuario} existe."
                )

            regla = (
                f"{usuario} ALL=(ALL:ALL) NOPASSWD: ALL"
            )

            contenido = (
                "# Escenario E4b - laboratorio aislado\n"
                "# Regla simulada, no instalada en sudoers\n"
                f"# Revision experimental {n}\n"
                f"{regla}\n"
            )

            hash_esperado = hashlib.sha256(
                contenido.encode("utf-8")
            ).hexdigest()

            inicio = ahora()

            escritura = ejecutar(
                ["sudo", "-n", "tee", ARCHIVO],
                entrada=contenido,
            )

            fin = ahora()

            lectura = ejecutar([
                "sudo", "-n", "cat", ARCHIVO
            ])

            contenido_ok = (
                lectura.returncode == 0
                and lectura.stdout == contenido
            )

            validacion = ejecutar([
                "sudo", "-n", "visudo", "-cf", ARCHIVO
            ])

            visudo_ok = validacion.returncode == 0

            correcto = (
                escritura.returncode == 0
                and contenido_ok
                and visudo_ok
            )

            writer.writerow({
                "repeticion": n,
                "variante": "E4b",
                "archivo": ARCHIVO,
                "usuario_ficticio": usuario,
                "regla_simulada": regla,
                "sha256_contenido": hash_esperado,
                "inicio_utc": inicio,
                "fin_utc": fin,
                "exit_code": escritura.returncode,
                "contenido_ok": int(contenido_ok),
                "visudo_ok": int(visudo_ok),
                "resultado_esperado": int(correcto),
                "naturaleza": "simulacion_sintetica",
                "amenaza": 1,
                "nivel": "ALTO",
            })

            archivo_csv.flush()

            print(
                f"E4b-{n}: escritura={escritura.returncode}, "
                f"contenido={'OK' if contenido_ok else 'ERROR'}, "
                f"visudo={'OK' if visudo_ok else 'ERROR'} "
                f"| {'OK' if correcto else 'REVISAR'}",
                flush=True,
            )

            if not correcto:
                print(escritura.stderr)
                print(validacion.stderr)
                sys.exit(
                    "ERROR: detener experimento y revisar."
                )

            if n < 10:
                time.sleep(PAUSAS[n - 1])

    if ejecutar([
        "sudo", "-n", "visudo", "-c"
    ]).returncode != 0:
        sys.exit(
            "ERROR: revisar configuracion real de sudo."
        )

    print("\nE4b finalizado.")
    print("Repeticiones:", 10)
    print("Archivo CSV:", OUTPUT)


if __name__ == "__main__":
    main()

