
import csv
import os
import pwd
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUTPUT = BASE / "data/raw/escenarios/e5a_ejecuciones.csv"

USUARIOS = ["gonzalo520", "root", "daemon"]

PAUSAS = [2, 3, 1, 4, 2, 3, 1, 2, 4]


def ahora():
    return datetime.now(timezone.utc).isoformat()


def ejecutar(comando):
    return subprocess.run(
        comando,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def verificar_entorno():
    if os.geteuid() == 0:
        sys.exit("ERROR: ejecutar como usuario normal.")

    if OUTPUT.exists():
        sys.exit(f"ERROR: el CSV ya existe: {OUTPUT}")

    if ejecutar(["sudo", "-n", "true"]).returncode != 0:
        sys.exit("ERROR: ejecutar sudo -v primero.")

    for usuario in USUARIOS:
        try:
            pwd.getpwnam(usuario)
        except KeyError:
            sys.exit(
                f"ERROR: no existe el usuario {usuario}"
            )

    for programa in (
        "/usr/bin/passwd",
        "/usr/bin/chage",
    ):
        if not Path(programa).is_file():
            sys.exit(
                f"ERROR: no existe {programa}"
            )


def main():
    verificar_entorno()

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    columnas = [
        "repeticion",
        "variante",
        "tipo_consulta",
        "usuario_consultado",
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
        "x",
        newline="",
        encoding="utf-8",
    ) as archivo:

        writer = csv.DictWriter(
            archivo,
            fieldnames=columnas,
        )

        writer.writeheader()
        archivo.flush()

        for n in range(1, 11):
            usuario = USUARIOS[
                (n - 1) % len(USUARIOS)
            ]

            if n % 2 == 1:
                tipo = "passwd_estado"
                comando = [
                    "sudo", "-n",
                    "/usr/bin/passwd",
                    "-S",
                    usuario,
                ]
            else:
                tipo = "chage_caducidad"
                comando = [
                    "sudo", "-n",
                    "/usr/bin/chage",
                    "-l",
                    usuario,
                ]

            print(
                f"\nE5a-{n}: {tipo} "
                f"({usuario})",
                flush=True,
            )

            inicio = ahora()

            try:
                resultado = ejecutar(comando)
            except subprocess.TimeoutExpired:
                sys.exit(
                    f"ERROR: timeout en E5a-{n}"
                )

            fin = ahora()

            correcto = resultado.returncode == 0

            writer.writerow({
                "repeticion": n,
                "variante": "E5a",
                "tipo_consulta": tipo,
                "usuario_consultado": usuario,
                "comando": shlex.join(comando),
                "inicio_utc": inicio,
                "fin_utc": fin,
                "exit_code": resultado.returncode,
                "resultado_esperado": int(correcto),
                "naturaleza": "consulta_administrativa",
                "amenaza": 0,
                "nivel": "INFO",
            })

            archivo.flush()

            print(
                f"  Exit code: "
                f"{resultado.returncode}"
            )
            print(
                f"  Correcto: {correcto}",
                flush=True,
            )

            if not correcto:
                print(
                    "ERROR: consulta fallida. "
                    "No se guarda la salida del comando."
                )
                sys.exit(
                    "Revisar antes de continuar."
                )

            if n < 10:
                time.sleep(PAUSAS[n - 1])

    print("\nE5a finalizado.")
    print("Repeticiones correctas: 10")
    print("Archivo CSV:", OUTPUT)


if __name__ == "__main__":
    main()

