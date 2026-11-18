
import argparse
import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from config_llm_a2 import (
    OPCIONES,
    ESQUEMA_RESPUESTA,
    NIVELES,
    TIPOS,
)
from prompts_llm import cargar_desarrollo
from prompts_fewshot_fijo import (
    cargar_protocolo,
    construir_fewshot_fijo,
)

BASE = Path(__file__).resolve().parent.parent
PROTOCOLO = BASE / "docs/protocolo_test_a2.json"
PROTOCOLO_FEWSHOT = (
    BASE / "results/llm_dev/"
    "protocolo_fewshot_fijo.json"
)
TEST = (
    BASE / "data/processed/dataset/"
    "prueba.jsonl"
)
SALIDAS = BASE / "results/llm_test"

URL = "http://127.0.0.1:11434"
MODELOS = ["qwen3:0.6b", "gemma3:1b"]


def sha256_bytes(datos):
    return hashlib.sha256(datos).hexdigest()


def sha256_archivo(ruta):
    return sha256_bytes(ruta.read_bytes())


def hash_objeto(objeto):
    contenido = json.dumps(
        objeto,
        sort_keys=True,
        ensure_ascii=False,
    )
    return sha256_bytes(contenido.encode("utf-8"))


def obtener_json(url):
    with urllib.request.urlopen(
        url, timeout=20
    ) as respuesta:
        return json.load(respuesta)


def cargar_eventos():
    eventos = []

    with TEST.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            original = json.loads(linea)

            # No incorporar etiquetas ni fuentes de test.
            eventos.append({
                "event_id": original["event_id"],
                "texto": original["texto"],
            })

    ids = [e["event_id"] for e in eventos]

    if len(eventos) != 361:
        raise ValueError("Test no contiene 361 eventos")

    if len(set(ids)) != 361:
        raise ValueError("IDs repetidos")

    return eventos


def preparar(modelo):
    with PROTOCOLO.open(
        encoding="utf-8"
    ) as archivo:
        congelado = json.load(archivo)

    if congelado["estado"] != "CONGELADO_ANTES_DE_TEST":
        raise ValueError("Protocolo no congelado")

    if congelado["opciones"] != OPCIONES:
        raise ValueError("Opciones modificadas")

    if congelado["esquema_respuesta"] != ESQUEMA_RESPUESTA:
        raise ValueError("Esquema modificado")

    if congelado["modelos"][modelo]["prompt"] != "few_shot_fijo":
        raise ValueError("Prompt seleccionado incorrecto")

    for nombre, esperado in congelado["sha256_codigo"].items():
        if sha256_archivo(BASE / nombre) != esperado:
            raise ValueError("Codigo modificado: " + nombre)

    if (
        sha256_archivo(PROTOCOLO_FEWSHOT)
        != congelado["protocolo_dev"]["sha256_archivo"]
    ):
        raise ValueError("Protocolo few-shot modificado")

    desarrollo = cargar_desarrollo()
    _, ejemplos = cargar_protocolo(desarrollo)

    ids_ejemplos = [e["event_id"] for e in ejemplos]

    if ids_ejemplos != congelado["ejemplos"]["ids"]:
        raise ValueError("Ejemplos modificados")

    for ejemplo in ejemplos:
        identificador = ejemplo["event_id"]
        esperado = congelado["ejemplos"][
            "sha256_textos"
        ][identificador]

        if sha256_bytes(
            ejemplo["texto"].encode("utf-8")
        ) != esperado:
            raise ValueError(
                "Texto de ejemplo modificado"
            )

    eventos = cargar_eventos()

    if set(ids_ejemplos) & {
        e["event_id"] for e in eventos
    }:
        raise ValueError(
            "Ejemplos presentes en test"
        )

    prompts = {}

    for evento in eventos:
        texto = construir_fewshot_fijo(
            evento, ejemplos
        )

        if (
            not texto.endswith("RESPUESTA JSON:")
            or len(texto.encode("utf-8")) > 12000
        ):
            raise ValueError(
                "Prompt invalido: " + evento["event_id"]
            )

        prompts[evento["event_id"]] = texto

    return congelado, eventos, prompts


def verificar_ollama(modelo, congelado):
    resultado = subprocess.run(
        ["ollama", "--version"],
        text=True,
        capture_output=True,
        check=True,
    )

    version = resultado.stdout.strip()

    if congelado["ollama_version"] not in version:
        raise ValueError(
            "Version de Ollama diferente: " + version
        )

    datos = obtener_json(URL + "/api/tags")

    disponibles = {
        m["name"]: m
        for m in datos["models"]
    }

    if modelo not in disponibles:
        raise ValueError("Modelo no instalado")

    esperado = congelado["modelos"][modelo]["id"]
    digest = disponibles[modelo]["digest"]

    if not digest.startswith(esperado):
        raise ValueError("Digest de modelo diferente")

    return version, digest



def rss_ollama_bytes():
    """
    Mide el RSS combinado de los procesos
    relacionados con Ollama:

    - ollama
    - llama-server

    La suma de RSS es aproximada porque
    las paginas compartidas pueden
    contabilizarse mas de una vez.
    """

    total = 0

    nombres_validos = {
        "ollama",
        "llama-server",
    }

    for nombre in os.listdir("/proc"):
        if not nombre.isdigit():
            continue

        base = Path("/proc") / nombre

        try:
            proceso = (
                (base / "comm")
                .read_text()
                .strip()
            )

            if proceso not in nombres_validos:
                continue

            with (base / "status").open() as archivo:
                for linea in archivo:
                    if linea.startswith("VmRSS:"):
                        kb = int(linea.split()[1])
                        total += kb * 1024
                        break

        except (
            FileNotFoundError,
            ProcessLookupError,
            PermissionError,
            ValueError,
        ):
            continue

    return total



class MonitorRAM:
    def __init__(self):
        self.maximo = 0
        self.ultimo = 0
        self.detener = threading.Event()
        self.hilo = None

    def muestrear(self):
        while not self.detener.is_set():
            valor = rss_ollama_bytes()

            self.ultimo = valor
            self.maximo = max(self.maximo, valor)

            self.detener.wait(0.1)

    def iniciar(self):
        self.hilo = threading.Thread(
            target=self.muestrear,
            daemon=True,
        )
        self.hilo.start()

    def finalizar(self):
        self.detener.set()

        if self.hilo is not None:
            self.hilo.join()


def validar_prediccion(pred):
    if not isinstance(pred, dict):
        return False, "JSON no es objeto"

    if set(pred) != {
        "amenaza", "nivel", "tipo", "explicacion"
    }:
        return False, "Campos incorrectos"

    if type(pred["amenaza"]) is not bool:
        return False, "Amenaza no booleana"

    if pred["nivel"] not in NIVELES:
        return False, "Nivel incorrecto"

    if pred["tipo"] not in TIPOS:
        return False, "Tipo incorrecto"

    if (
        not isinstance(pred["explicacion"], str)
        or not pred["explicacion"].strip()
    ):
        return False, "Explicacion incorrecta"

    if pred["amenaza"] != (pred["nivel"] != "INFO"):
        return False, "Amenaza y nivel incoherentes"

    return True, None


def inferir(modelo, prompt):
    solicitud = {
        "model": modelo,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": ESQUEMA_RESPUESTA,
        "options": OPCIONES,
        "keep_alive": "5m",
    }

    datos = json.dumps(
        solicitud,
        ensure_ascii=False,
    ).encode("utf-8")

    peticion = urllib.request.Request(
        URL + "/api/generate",
        data=datos,
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    inicio = time.perf_counter()

    with urllib.request.urlopen(
        peticion, timeout=300
    ) as respuesta:
        resultado = json.load(respuesta)

    tiempo = time.perf_counter() - inicio

    original = resultado.get("response", "")

    try:
        prediccion = json.loads(original)
        valido, motivo = validar_prediccion(
            prediccion
        )
    except (json.JSONDecodeError, TypeError):
        prediccion = None
        valido = False
        motivo = "Respuesta no es JSON valido"

    entrada = resultado.get("prompt_eval_count")
    salida = resultado.get("eval_count")

    revisar_contexto = (
        type(entrada) is not int
        or entrada < 0
        or entrada >= (
            OPCIONES["num_ctx"]
            - OPCIONES["num_predict"]
        )
        or resultado.get("done") is not True
    )

    return {
        "prediccion": prediccion,
        "respuesta_original": original,
        "valido": valido,
        "motivo_invalidez": motivo,
        "tiempo_s": tiempo,
        "prompt_eval_count": entrada,
        "eval_count": salida,
        "done": resultado.get("done"),
        "done_reason": resultado.get("done_reason"),
        "contexto_revisar": revisar_contexto,
        "salida_limitada": (
            resultado.get("done_reason") == "length"
        ),
        "total_duration_ns": resultado.get(
            "total_duration"
        ),
        "load_duration_ns": resultado.get(
            "load_duration"
        ),
    }


def cargar_previos(ruta):
    anteriores = {}

    if not ruta.exists():
        return anteriores

    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            fila = json.loads(linea)
            identificador = fila["event_id"]

            if identificador in anteriores:
                raise ValueError(
                    "Resultado duplicado"
                )

            anteriores[identificador] = fila

    return anteriores


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--modelo",
        required=True,
        choices=MODELOS,
    )

    parser.add_argument(
        "--corrida",
        type=int,
        required=True,
        choices=[1, 2, 3],
    )

    parser.add_argument(
        "--preflight",
        action="store_true",
    )

    args = parser.parse_args()

    congelado, eventos, prompts = preparar(
        args.modelo
    )

    version, digest = verificar_ollama(
        args.modelo, congelado
    )

    nombre = args.modelo.replace(":", "_")

    base_nombre = (
        f"{nombre}_corrida_{args.corrida}"
    )

    salida = SALIDAS / (base_nombre + ".jsonl")
    resumen_ruta = SALIDAS / (
        base_nombre + "_recursos.json"
    )

    configuracion = {
        "modelo": args.modelo,
        "digest": digest,
        "corrida": args.corrida,
        "prompt": "few_shot_fijo",
        "opciones": OPCIONES,
        "formato": ESQUEMA_RESPUESTA,
        "ids_ejemplos": congelado["ejemplos"]["ids"],
        "commit_fuente": congelado["commit_fuente"],
    }

    hash_config = hash_objeto(configuracion)

    print("=" * 60)
    print("INFERENCIA TEST - A2")
    print("=" * 60)
    print("Modelo:", args.modelo)
    print("Corrida:", args.corrida)
    print("Ollama:", version)
    print("Digest:", digest)
    print("Eventos:", len(eventos))
    print("Prompt:", "few_shot_fijo")
    print("Hash config:", hash_config)

    if args.preflight:
        print(
            "\nPRE-FLIGHT: OK "
            "(no se realizaron inferencias)"
        )
        return

    if resumen_ruta.exists():
        raise SystemExit(
            "La corrida ya fue finalizada."
        )

    SALIDAS.mkdir(
        parents=True, exist_ok=True
    )

    previos = cargar_previos(salida)

    ids_esperados = {
        e["event_id"] for e in eventos
    }

    if not set(previos).issubset(ids_esperados):
        raise ValueError(
            "Hay resultados ajenos al test"
        )

    for identificador, fila in previos.items():
        if (
            fila["hash_config"] != hash_config
            or fila["hash_prompt"] != sha256_bytes(
                prompts[identificador].encode("utf-8")
            )
        ):
            raise ValueError(
                "Configuracion de reanudacion diferente"
            )

        if fila.get("contexto_revisar"):
            raise ValueError(
                "Un evento anterior requiere "
                "revision del contexto"
            )

    print("Ya procesados:", len(previos))

    monitor = MonitorRAM()
    monitor.iniciar()

    inicio_corrida = time.perf_counter()

    try:
        with salida.open(
            "a", encoding="utf-8"
        ) as archivo:
            for evento in eventos:
                identificador = evento["event_id"]

                if identificador in previos:
                    continue

                prompt = prompts[identificador]

                # En esta etapa no se consultan
                # etiquetas de referencia.
                respuesta = inferir(
                    args.modelo, prompt
                )

                fila = {
                    "event_id": identificador,
                    "serial": identificador.split(":")[-1],
                    "modelo": args.modelo,
                    "corrida": args.corrida,
                    "estrategia": "few_shot_fijo",
                    "ids_ejemplos": congelado[
                        "ejemplos"
                    ]["ids"],
                    "hash_config": hash_config,
                    "hash_prompt": sha256_bytes(
                        prompt.encode("utf-8")
                    ),
                    **respuesta,
                }

                archivo.write(
                    json.dumps(
                        fila,
                        ensure_ascii=False,
                    ) + "\n"
                )
                archivo.flush()

                previos[identificador] = fila

                if (
                    len(previos) % 10 == 0
                    or len(previos) == 361
                ):
                    print(
                        f"Procesados: "
                        f"{len(previos)}/361",
                        flush=True,
                    )

                if respuesta["contexto_revisar"]:
                    raise RuntimeError(
                        "REVISAR CONTEXTO: "
                        + identificador
                    )

    finally:
        monitor.finalizar()

    if len(previos) != 361:
        raise ValueError(
            "La corrida no esta completa"
        )

    tiempo_total = (
        time.perf_counter() - inicio_corrida
    )

    resumen = {
        "modelo": args.modelo,
        "corrida": args.corrida,
        "hash_config": hash_config,
        "eventos": 361,
        "tiempo_ejecucion_s": tiempo_total,
        "ram_pico_rss_ollama_bytes": monitor.maximo,
        "ram_pico_rss_ollama_mib": (
            monitor.maximo / (1024 ** 2)
        ),
        "metodo_ram": (
	    "Muestreo cada 100 ms de la suma de VmRSS "
	    "de los procesos ollama y llama-server "
	    "identificados mediante /proc. "
	    "La memoria compartida puede "
	    "contabilizarse mas de una vez."
	),
        "invalidos": sum(
            not fila["valido"]
            for fila in previos.values()
        ),
        "contexto_marcado": sum(
            bool(fila["contexto_revisar"])
            for fila in previos.values()
        ),
        "salidas_limitadas": sum(
            bool(fila["salida_limitada"])
            for fila in previos.values()
        ),
    }

    with resumen_ruta.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            resumen,
            archivo,
            indent=2,
            ensure_ascii=False,
        )

    print("\n" + "=" * 60)
    print("CORRIDA FINALIZADA")
    print("=" * 60)
    print("Modelo:", args.modelo)
    print("Corrida:", args.corrida)
    print("Eventos:", len(previos))
    print("Invalidos:", resumen["invalidos"])
    print(
        "RAM pico aproximada:",
        f'{resumen["ram_pico_rss_ollama_mib"]:.2f} MiB'
    )
    print("Archivo:", salida)
    print("Recursos:", resumen_ruta)
    print("\nINFERENCIA TEST: OK")


if __name__ == "__main__":
    main()

