
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
OUTPUT_FILE = OUTPUT_DIR / "e2_ejecuciones.csv"

USUARIOS = ["nobody", "daemon"]

RUTAS_SUID = [
    ["/usr/bin"],
    ["/usr/sbin"],
    ["/usr/bin", "/usr/sbin"],
    ["/bin"],
    ["/sbin"],
]

ORDENES = [
    ["sudo", "su", "find"],
    ["find", "sudo", "su"],
    ["sudo", "find", "su"],
    ["find", "su", "sudo"],
    ["su", "sudo", "find"],
]

PAUSAS = [2, 3, 1, 4, 2, 3, 4, 1, 2]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def verificar_entorno():
    if os.geteuid() != 0:
        sys.exit(
            "ERROR: ejecutar con sudo python3 "
            "scripts/generar_e2.py"
        )

    usuario_original = os.environ.get("SUDO_USER")

    if not usuario_original or usuario_original == "root":
        sys.exit("ERROR: utilizar sudo desde una cuenta normal.")

    for usuario in USUARIOS:
        try:
            pwd.getpwnam(usuario)
        except KeyError:
            sys.exit(f"ERROR: no existe {usuario}")

    for programa in ["runuser", "sudo", "su", "find", "timeout"]:
        if shutil.which(programa) is None:
            sys.exit(f"ERROR: falta {programa}")

    if OUTPUT_FILE.exists():
        sys.exit(
            f"ERROR: ya existe {OUTPUT_FILE}. "
            "No se sobrescriben resultados anteriores."
        )

    return usuario_original


def obtener_comando(accion, rutas):
    if accion == "sudo":
        return ["/usr/bin/sudo", "-n", "-l"]

    if accion == "su":
        return [
            "/usr/bin/timeout",
            "6s",
            "/usr/bin/su",
            "-c",
            "/usr/bin/id",
            "root",
        ]

    if accion == "find":
        return [
            "/usr/bin/find",
            *rutas,
            "-xdev",
            "-type",
            "f",
            "-perm",
            "/4000",
            "-print",
        ]

    raise ValueError(f"Accion desconocida: {accion}")


def ejecutar_accion(usuario, comando):
    comando_completo = [
        "/usr/sbin/runuser",
        "-u",
        usuario,
        "--",
        *comando,
    ]

    inicio = utc_now()

    try:
        resultado = subprocess.run(
            comando_completo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=12,
            check=False,
        )

        codigo = resultado.returncode
        error = resultado.stderr.strip()

    except subprocess.TimeoutExpired:
        codigo = 124
        error = "Tiempo limite excedido"

    fin = utc_now()

    return inicio, fin, codigo, error


def resultado_esperado(accion, codigo):
    if accion in ("sudo", "su"):
        return codigo == 1

    if accion == "find":
        return codigo == 0

    return False


def main():
    usuario_original = verificar_entorno()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    columnas = [
        "repeticion",
        "variante",
        "accion",
        "usuario_ejecutor",
        "comando",
        "inicio_utc",
        "fin_utc",
        "exit_code",
        "resultado_esperado",
        "amenaza_secuencia",
        "nivel_esperado_secuencia",
    ]

    total_acciones = 0
    inesperados = 0

    try:
        with OUTPUT_FILE.open(
            "x", newline="", encoding="utf-8"
        ) as archivo:

            writer = csv.DictWriter(
                archivo, fieldnames=columnas
            )
            writer.writeheader()

            for numero in range(1, 11):
                usuario = USUARIOS[(numero - 1) % len(USUARIOS)]
                rutas = RUTAS_SUID[
                    (numero - 1) % len(RUTAS_SUID)
                ]
                orden = ORDENES[
                    (numero - 1) % len(ORDENES)
                ]

                print(
                    f"\nE2 - secuencia {numero}/10 "
                    f"(usuario={usuario})"
                )

                for accion in orden:
                    comando = obtener_comando(accion, rutas)

                    inicio, fin, codigo, error = ejecutar_accion(
                        usuario, comando
                    )

                    esperado = resultado_esperado(accion, codigo)

                    writer.writerow({
                        "repeticion": numero,
                        "variante": "E2",
                        "accion": accion,
                        "usuario_ejecutor": usuario,
                        "comando": shlex.join(comando),
                        "inicio_utc": inicio,
                        "fin_utc": fin,
                        "exit_code": codigo,
                        "resultado_esperado": int(esperado),
                        "amenaza_secuencia": 1,
                        "nivel_esperado_secuencia": "MEDIO",
                    })

                    archivo.flush()
                    total_acciones += 1

                    print(
                        f"  {accion}: exit={codigo} "
                        f"| esperado={esperado}"
                    )

                    if not esperado:
                        inesperados += 1
                        print(f"  Detalle: {error}")

                        # No continuar si se concedieron privilegios.
                        if accion in ("sudo", "su") and codigo == 0:
                            sys.exit(
                                "ALERTA: una operacion de "
                                "privilegios tuvo exito. "
                                "Ejecucion detenida."
                            )

                    time.sleep(0.5)

                if numero < 10:
                    time.sleep(PAUSAS[numero - 1])

    finally:
        if OUTPUT_FILE.exists():
            propietario = pwd.getpwnam(usuario_original)

            os.chown(
                OUTPUT_FILE,
                propietario.pw_uid,
                propietario.pw_gid,
            )

    print("\nGeneracion E2 finalizada.")
    print("Secuencias previstas: 10")
    print(f"Acciones registradas: {total_acciones}")
    print(f"Resultados inesperados: {inesperados}")
    print(f"Archivo: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

