
import json

from clasificador_regex import detectar_reglas

NIVELES = ("INFO", "BAJO", "MEDIO", "ALTO")

TIPOS = {
    "actividad_normal",
    "anomalia_operativa",
    "autenticacion",
    "reconocimiento",
    "anomalia_privilegios",
    "acceso_sensible",
    "modificacion_configuracion",
    "otro",
}


def crear_resultado(amenaza, nivel, tipo, explicacion):
    resultado = {
        "amenaza": amenaza,
        "nivel": nivel,
        "tipo": tipo,
        "explicacion": explicacion,
    }

    validar_resultado(resultado)
    return resultado


def validar_resultado(resultado):
    if not isinstance(resultado, dict):
        raise ValueError("La salida debe ser JSON objeto")

    campos = {"amenaza", "nivel", "tipo", "explicacion"}

    if set(resultado) != campos:
        raise ValueError("Campos JSON incorrectos")

    if not isinstance(resultado["amenaza"], bool):
        raise ValueError("amenaza debe ser booleano")

    if resultado["nivel"] not in NIVELES:
        raise ValueError("Nivel invalido")

    if resultado["tipo"] not in TIPOS:
        raise ValueError("Tipo invalido")

    if (
        not isinstance(resultado["explicacion"], str)
        or not resultado["explicacion"].strip()
    ):
        raise ValueError("Explicacion invalida")

    if resultado["amenaza"] != (
        resultado["nivel"] != "INFO"
    ):
        raise ValueError(
            "Inconsistencia entre amenaza y nivel"
        )

    return True


def clasificar_evento(texto):
    if not isinstance(texto, str):
        raise TypeError("El evento debe ser texto")

    reglas = set(detectar_reglas(texto))

    # Prioridad 1: acceso sospechoso a credenciales.
    if "R4_SHADOW_GENERICO" in reglas:
        return crear_resultado(
            True,
            "ALTO",
            "acceso_sensible",
            "Se observa un acceso a /etc/shadow "
            "mediante cat o cp. Requiere investigacion.",
        )

    # Prioridad 2: anomalia de identidad efectiva.
    if "R3_UID_EUID" in reglas:
        return crear_resultado(
            True,
            "MEDIO",
            "anomalia_privilegios",
            "Se observa bash o id con UID no "
            "privilegiado y EUID root.",
        )

    # Prioridad 3: autenticacion fallida.
    if "R2_AUTH_FALLIDA" in reglas:
        return crear_resultado(
            True,
            "MEDIO",
            "autenticacion",
            "El evento contiene un resultado de "
            "autenticacion fallida.",
        )

    # Prioridad 4: uso de su.
    if "R1_SU" in reglas:
        return crear_resultado(
            True,
            "MEDIO",
            "autenticacion",
            "Se observa una ejecucion de su que "
            "requiere revision de seguridad.",
        )

    # Anomalia operativa sin indicadores de amenaza.
    if any(
        linea.startswith("tipo=ANOM_ABEND")
        for linea in texto.splitlines()
    ):
        return crear_resultado(
            False,
            "INFO",
            "anomalia_operativa",
            "Se registra una terminacion anomala "
            "de proceso, sin evidencia suficiente "
            "de una amenaza de seguridad.",
        )

    # Comportamiento sin indicadores detectados.
    return crear_resultado(
        False,
        "INFO",
        "actividad_normal",
        "No se detectaron indicadores de amenaza "
        "mediante las reglas definidas.",
    )


if __name__ == "__main__":
    ejemplo = (
        "tipo=SYSCALL syscall=257 success=yes "
        "uid=1000 euid=1000 comm=cat "
        "exe=/usr/bin/cat\n"
        "tipo=PATH ruta=/etc/shadow"
    )

    resultado = clasificar_evento(ejemplo)

    print(json.dumps(
        resultado,
        ensure_ascii=False,
        indent=2,
    ))

    print("\nVALIDACION REGEX MULTICLASE: OK")

