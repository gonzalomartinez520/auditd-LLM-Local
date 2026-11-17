
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/processed/dataset"

ENTRADA = DATA / "eventos_unificados.jsonl"
SALIDA = DATA / "eventos_normalizados.jsonl"
RESUMEN = DATA / "resumen_normalizacion.json"

TOTAL_ESPERADO = 519

# Campos de auditoria que se conservaran.
CAMPOS_SYSCALL = [
    "arch", "syscall", "success",
    "auid", "uid", "euid", "suid", "fsuid",
    "gid", "egid", "comm", "exe",
]

CAMPOS_PATH = [
    "nametype", "mode",
]

CAMPOS_AUTENTICACION = [
    "op", "res",
]

MARCADORES_PROHIBIDOS = re.compile(
    r"key=|a2_exec|a2_file_access|"
    r"a2_config_access|a2_e4b_lab|"
    r"a2_e4a|a2-e4b-lab|"
    r"\be[1-5][ab]?[-_](?:ataque|control|lab)\b",
    re.IGNORECASE,
)

PATRON_TIPO = re.compile(r"^type=([A-Z_]+)")


def obtener_campo(registro, nombre):
    patron = (
        rf'(?:^|\s){re.escape(nombre)}='
        rf'(?:"([^"]*)"|([^\s\x1d]+))'
    )

    coincidencia = re.search(patron, registro)

    if coincidencia is None:
        return None

    if coincidencia.group(1) is not None:
        return coincidencia.group(1)

    return coincidencia.group(2)


def normalizar_ruta(ruta):
    if not ruta:
        return None

    # El archivo de E4b estaba fuera de sudoers.
    # Se conserva esa distincion.
    if ruta.startswith("/var/tmp/a2-e4b-lab"):
        return "/var/tmp/<directorio_prueba>/<archivo_prueba>"

    if ruta.startswith("/etc/sudoers.d/a2_e4a"):
        return "/etc/sudoers.d/<archivo_prueba>"

    # Conservar rutas absolutas reconocibles.
    # Evitar texto arbitrario o campos codificados.
    if not ruta.startswith("/"):
        return "<ruta_no_absoluta>"

    if any(ord(c) < 32 for c in ruta):
        return "<ruta_no_valida>"

    # Seudonimizar directorios personales.
    ruta = re.sub(
        r"^/home/[^/]+",
        "/home/<usuario>",
        ruta,
    )

    # Otras rutas experimentales explicitas.
    ruta = re.sub(
        r"a2[_-]e[1-5][ab]?[^/]*",
        "<archivo_prueba>",
        ruta,
        flags=re.IGNORECASE,
    )

    return ruta


def normalizar_registro(registro):
    coincidencia = PATRON_TIPO.match(registro)

    if coincidencia is None:
        return None, None

    tipo = coincidencia.group(1)

    # Se excluyen contenidos y argumentos potencialmente
    # sensibles o codificados en esta primera version.
    if tipo in {"PROCTITLE", "CWD"}:
        return tipo, None

    partes = [f"tipo={tipo}"]

    if tipo == "SYSCALL":
        for campo in CAMPOS_SYSCALL:
            valor = obtener_campo(registro, campo)

            if valor is not None:
                partes.append(f"{campo}={valor}")

        syscall = obtener_campo(registro, "syscall")

        # En openat, a2 contiene los flags de apertura.
        if syscall in {"openat", "257"}:
            flags = obtener_campo(registro, "a2")

            if flags is not None:
                partes.append(f"flags_openat={flags}")

        # El errno resulta util para detectar fallos.
        if obtener_campo(registro, "success") == "no":
            salida = obtener_campo(registro, "exit")

            if salida is not None:
                partes.append(f"exit={salida}")

    elif tipo == "PATH":
        ruta = normalizar_ruta(
            obtener_campo(registro, "name")
        )

        if ruta is not None:
            partes.append(f"ruta={ruta}")

        for campo in CAMPOS_PATH:
            valor = obtener_campo(registro, campo)

            if valor is not None:
                partes.append(f"{campo}={valor}")

    elif tipo.startswith("USER_") or tipo in {
        "CRED_ACQ", "CRED_DISP", "CRED_REFR",
        "LOGIN",
    }:
        for campo in CAMPOS_AUTENTICACION:
            valor = obtener_campo(registro, campo)

            if valor is not None:
                # Evitar incorporar mensajes arbitrarios.
                if re.fullmatch(r"[A-Za-z0-9_.:/-]+", valor):
                    partes.append(f"{campo}={valor}")

    elif tipo == "ANOM_ABEND":
        for campo in ("sig", "comm", "exe"):
            valor = obtener_campo(registro, campo)

            if valor is not None:
                partes.append(f"{campo}={valor}")

    # EXECVE se conserva como tipo, pero sin argv.
    # Otros registros conservan solo su tipo.

    return tipo, " ".join(partes)


def main():
    if not ENTRADA.is_file():
        raise SystemExit(f"ERROR: falta {ENTRADA}")

    for ruta in (SALIDA, RESUMEN):
        if ruta.exists():
            raise SystemExit(
                f"ERROR: ya existe {ruta}. "
                "No se sobrescribira."
            )

    normalizados = []
    identificadores = set()

    tipos_originales = Counter()
    tipos_conservados = Counter()
    tipos_omitidos = Counter()

    for numero_linea, linea in enumerate(
        ENTRADA.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not linea.strip():
            continue

        evento = json.loads(linea)
        event_id = evento.get("event_id")
        registros = evento.get("records")

        if not isinstance(event_id, str) or not event_id:
            raise ValueError(
                f"Linea {numero_linea}: event_id invalido"
            )

        if event_id in identificadores:
            raise ValueError(
                f"event_id duplicado: {event_id}"
            )

        if not isinstance(registros, list) or not registros:
            raise ValueError(
                f"Evento {event_id}: records invalidos"
            )

        lineas_normalizadas = []

        for registro in registros:
            if not isinstance(registro, str):
                raise ValueError(
                    f"Evento {event_id}: registro no textual"
                )

            tipo, texto = normalizar_registro(registro)

            if tipo is None:
                continue

            tipos_originales[tipo] += 1

            if texto is None:
                tipos_omitidos[tipo] += 1
                continue

            lineas_normalizadas.append(texto)
            tipos_conservados[tipo] += 1

        if not lineas_normalizadas:
            raise ValueError(
                f"Evento {event_id}: sin datos normalizados"
            )

        texto_final = "\n".join(lineas_normalizadas)

        if MARCADORES_PROHIBIDOS.search(texto_final):
            raise ValueError(
                f"Marcador experimental detectado: {event_id}"
            )

        normalizados.append({
            "event_id": event_id,
            "texto": texto_final,
        })

        identificadores.add(event_id)

    if len(normalizados) != TOTAL_ESPERADO:
        raise ValueError(
            f"Esperados {TOTAL_ESPERADO} eventos, "
            f"obtenidos {len(normalizados)}"
        )

    resumen = {
        "eventos_originales": TOTAL_ESPERADO,
        "eventos_normalizados": len(normalizados),
        "identificadores_unicos": len(identificadores),
        "duplicados": 0,
        "tipos_originales": dict(tipos_originales),
        "tipos_conservados": dict(tipos_conservados),
        "tipos_omitidos": dict(tipos_omitidos),
        "proctitle_excluido": True,
        "execve_argumentos_excluidos": True,
        "claves_auditoria_excluidas": True,
        "etiquetas_excluidas": True,
    }

    # Solo escribir despues de validar en memoria.
    with SALIDA.open("x", encoding="utf-8") as archivo:
        for evento in normalizados:
            archivo.write(
                json.dumps(
                    evento, ensure_ascii=False
                ) + "\n"
            )

    with RESUMEN.open("x", encoding="utf-8") as archivo:
        json.dump(
            resumen,
            archivo,
            indent=2,
            ensure_ascii=False,
        )

    print("=" * 58)
    print("NORMALIZACION DE EVENTOS - TP FINAL A2")
    print("=" * 58)

    print("Eventos originales:", TOTAL_ESPERADO)
    print("Eventos normalizados:", len(normalizados))
    print("Identificadores unicos:", len(identificadores))
    print("Duplicados:", 0)

    print("\nREGISTROS OMITIDOS")
    for tipo, cantidad in tipos_omitidos.most_common():
        print(f"{tipo:<20} {cantidad:>6}")

    print("\nREGISTROS CONSERVADOS")
    for tipo, cantidad in tipos_conservados.most_common():
        print(f"{tipo:<20} {cantidad:>6}")

    print("\nClaves de auditoria: excluidas")
    print("Argumentos EXECVE: excluidos")
    print("PROCTITLE: excluido")
    print("Etiquetas experimentales: excluidas")

    print("\nVALIDACION GENERAL: OK")
    print("Salida:", SALIDA)


if __name__ == "__main__":
    main()

