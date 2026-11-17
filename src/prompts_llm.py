
import csv
import json
from pathlib import Path

from config_llm_a2 import ESTRATEGIAS

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/processed/dataset"

DEV = DATA / "desarrollo.jsonl"
ETIQUETAS = DATA / "etiquetas_multiclase.csv"

INSTRUCCIONES = """
Eres un analizador de seguridad de sistemas Linux.

Recibiras UN evento de auditoria completo, representado
mediante registros normalizados de auditd.

Clasifica la actividad segun las evidencias observables.

Niveles:
INFO: sin evidencia concreta de amenaza de seguridad.
BAJO: actividad potencialmente sospechosa de bajo riesgo.
MEDIO: indicadores relevantes de autenticacion,
reconocimiento o anomalias de privilegios.
ALTO: indicios de riesgo elevado relacionados con
credenciales o configuraciones criticas.


REGLAS OBLIGATORIAS DE COHERENCIA:

Determina primero el nivel de severidad y luego
asigna el valor de amenaza correspondiente.

La correspondencia es estricta:

- INFO  -> amenaza = false
- BAJO  -> amenaza = true
- MEDIO -> amenaza = true
- ALTO  -> amenaza = true

Si no existen indicadores concretos de amenaza,
selecciona INFO, nunca BAJO.

BAJO no significa actividad normal. Representa
una actividad sospechosa de riesgo bajo.

No utilices modificacion_configuracion simplemente
porque aparezca un archivo de configuracion.
Debe existir evidencia observable de una operacion
de modificacion.

No afirmes que se modifico un archivo si el registro
solo demuestra lectura, apertura o acceso.

No supongas el contenido de un archivo modificado
cuando ese contenido no esta disponible.

Elige un tipo coherente con el proceso y la operacion
observados. Si no hay indicadores concretos de amenaza,
puedes utilizar actividad_normal u otro tipo justificado.

Antes de responder, verifica internamente que:
1. amenaza coincide con el nivel seleccionado.
2. tipo coincide con la evidencia disponible.
3. explicacion no contradice los otros campos.
4. Los cuatro campos JSON estan presentes.

No incluyas esta verificacion en la respuesta.
Devuelve solamente el JSON solicitado.


Tipos permitidos:
actividad_normal, anomalia_operativa, autenticacion,
reconocimiento, anomalia_privilegios, acceso_sensible,
modificacion_configuracion, otro.

Considera que:
- Una operacion realizada por root puede ser legitima.
- Un acceso a /etc/shadow no demuestra por si mismo
  una actividad maliciosa.
- El proceso, sus privilegios y el resultado importan.
- Una operacion fallida puede ser relevante.
- La ausencia de informacion no demuestra un ataque.
- No inventes acciones ni contenidos no registrados.
- Un fallo operativo no implica necesariamente un
  ataque de seguridad.

Devuelve unicamente un objeto JSON con exactamente:
amenaza, nivel, tipo, explicacion.

La explicacion debe ser breve, concreta y basarse
exclusivamente en el evento observado.
""".strip()


def cargar_desarrollo():
    with ETIQUETAS.open(
        newline="", encoding="utf-8"
    ) as archivo:
        todas = {
            fila["event_id"]: fila
            for fila in csv.DictReader(archivo)
        }

    eventos = []

    with DEV.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            evento = json.loads(linea)
            identificador = evento["event_id"]

            if identificador not in todas:
                raise ValueError(
                    f"Sin etiqueta: {identificador}"
                )

            eventos.append({
                "event_id": identificador,
                "texto": evento["texto"],
                "etiqueta": todas[identificador],
            })

    if len(eventos) != 158:
        raise ValueError(
            "Desarrollo debe contener 158 eventos"
        )

    if len({e["event_id"] for e in eventos}) != 158:
        raise ValueError("IDs duplicados en desarrollo")

    return eventos


def ejemplo_json(etiqueta):
    return {
        "amenaza": etiqueta["amenaza"] == "1",
        "nivel": etiqueta["nivel"],
        "tipo": etiqueta["tipo"],
        "explicacion": (
            "Ejemplo etiquetado de referencia "
            "del conjunto de desarrollo."
        ),
    }


def seleccionar_ejemplos(objetivo, desarrollo):
    candidatos = []

    etiqueta_objetivo = objetivo["etiqueta"]

    for candidato in desarrollo:
        etiqueta = candidato["etiqueta"]

        if candidato["event_id"] == objetivo["event_id"]:
            continue

        if etiqueta["grupo"] == etiqueta_objetivo["grupo"]:
            continue

        # Evitar ejemplos de la misma variante.
        if etiqueta["fuente"] == etiqueta_objetivo["fuente"]:
            continue

        candidatos.append(candidato)

    seleccionados = []

    # No hay ejemplos BAJO en las etiquetas.
    for nivel in ("INFO", "MEDIO", "ALTO"):
        disponibles = [
            e for e in candidatos
            if e["etiqueta"]["nivel"] == nivel
        ]

        # Seleccion determinista; preferir eventos cortos
        # para preservar el contexto sin dividir eventos.
        disponibles.sort(
            key=lambda e: (
                len(e["texto"].encode("utf-8")),
                e["event_id"],
            )
        )

        if not disponibles:
            raise ValueError(
                f"Sin ejemplos de nivel {nivel} "
                f"para {objetivo['event_id']}"
            )

        seleccionados.append(disponibles[0])

    ids = [e["event_id"] for e in seleccionados]

    if objetivo["event_id"] in ids:
        raise ValueError("Filtracion del evento objetivo")

    if len(ids) != len(set(ids)):
        raise ValueError("Ejemplos duplicados")

    return seleccionados


def construir_prompt(estrategia, objetivo, desarrollo):
    if estrategia not in ESTRATEGIAS:
        raise ValueError(
            f"Estrategia desconocida: {estrategia}"
        )

    contenido = INSTRUCCIONES
    ids_ejemplos = []

    if estrategia == "few_shot":
        ejemplos = seleccionar_ejemplos(
            objetivo, desarrollo
        )

        contenido += (
            "\n\nEJEMPLOS RESUELTOS DE DESARROLLO:"
        )

        for numero, ejemplo in enumerate(
            ejemplos, start=1
        ):
            respuesta = ejemplo_json(
                ejemplo["etiqueta"]
            )

            contenido += (
                f"\n\nEjemplo {numero}:\n"
                f"{ejemplo['texto']}\n"
                "Respuesta:\n"
                + json.dumps(
                    respuesta,
                    ensure_ascii=False,
                )
            )

            ids_ejemplos.append(
                ejemplo["event_id"]
            )

        contenido += (
            "\n\nAplica los criterios a un evento nuevo. "
            "No copies automaticamente las respuestas "
            "de los ejemplos."
        )

    elif estrategia == "chain_of_thought":
        contenido += """
        
Antes de clasificar, examina sistematicamente:
1. Proceso y operacion observada.
2. UID, EUID y resultado si estan disponibles.
3. Archivos y recursos involucrados.
4. Indicadores de riesgo y explicaciones legitimas.
5. Nivel de severidad y tipo mas justificados.

Incluye una sintesis breve de ese analisis
en el campo explicacion.

No describas evidencias inexistentes.
""".rstrip()

    contenido += (
        "\n\nEVENTO A CLASIFICAR:\n"
        + objetivo["texto"]
        + "\n\nRESPUESTA JSON:"
    )

    return {
        "prompt": contenido,
        "ids_ejemplos": ids_ejemplos,
    }


if __name__ == "__main__":
    desarrollo = cargar_desarrollo()
    objetivo = desarrollo[0]

    for estrategia in ESTRATEGIAS:
        resultado = construir_prompt(
            estrategia, objetivo, desarrollo
        )

        print("=" * 55)
        print("ESTRATEGIA:", estrategia)
        print("Evento:", objetivo["event_id"])
        print("Ejemplos:", resultado["ids_ejemplos"])
        print(
            "Longitud en bytes:",
            len(resultado["prompt"].encode("utf-8"))
        )

    print("\nVALIDACION DE PROMPTS: OK")

