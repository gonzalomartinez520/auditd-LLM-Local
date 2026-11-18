
import json
import statistics
from collections import Counter
from pathlib import Path

from inferir_test_a2 import (
    BASE,
    preparar,
    hash_objeto,
    sha256_bytes,
    validar_prediccion,
)

CARPETA = BASE / "results/llm_test"
SALIDA = CARPETA / "auditoria_corridas.json"

DIGESTS = {
    "qwen3:0.6b":
        "7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435",
    "gemma3:1b":
        "97558784bdc9175075a72655bf360b15da17df6b3b9e5182af9f8c0c8e58ba7c",
}


def cargar_jsonl(ruta):
    filas = {}

    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            fila = json.loads(linea)
            identificador = fila["event_id"]

            if identificador in filas:
                raise ValueError(
                    f"ID duplicado: {identificador}"
                )

            filas[identificador] = fila

    return filas


def firma_prediccion(fila):
    if not fila["valido"]:
        return ("INVALIDA",)

    pred = fila["prediccion"]

    return (
        pred["amenaza"],
        pred["nivel"],
        pred["tipo"],
    )


def main():
    reporte = {
        "eventos_esperados": 361,
        "modelos": {},
    }

    for modelo, digest in DIGESTS.items():
        congelado, eventos, prompts = preparar(modelo)

        ids = [e["event_id"] for e in eventos]
        ids_esperados = set(ids)

        if len(ids_esperados) != 361:
            raise ValueError("Test inconsistente")

        corridas = {}
        recursos = {}

        nombre = modelo.replace(":", "_")

        for numero in (1, 2, 3):
            prefijo = f"{nombre}_corrida_{numero}"

            ruta = CARPETA / f"{prefijo}.jsonl"
            ruta_recursos = (
                CARPETA / f"{prefijo}_recursos.json"
            )

            filas = cargar_jsonl(ruta)

            with ruta_recursos.open(
                encoding="utf-8"
            ) as archivo:
                recurso = json.load(archivo)

            config = {
                "modelo": modelo,
                "digest": digest,
                "corrida": numero,
                "prompt": "few_shot_fijo",
                "opciones": congelado["opciones"],
                "formato": congelado["esquema_respuesta"],
                "ids_ejemplos":
                    congelado["ejemplos"]["ids"],
                "commit_fuente":
                    congelado["commit_fuente"],
            }

            hash_esperado = hash_objeto(config)

            if set(filas) != ids_esperados:
                raise ValueError(
                    f"IDs incorrectos: {prefijo}"
                )

            if (
                recurso["hash_config"] != hash_esperado
                or recurso["modelo"] != modelo
                or recurso["corrida"] != numero
                or recurso["eventos"] != 361
            ):
                raise ValueError(
                    f"Recursos inconsistentes: {prefijo}"
                )

            for identificador, fila in filas.items():
                hash_prompt = sha256_bytes(
                    prompts[identificador].encode("utf-8")
                )

                if (
                    fila["modelo"] != modelo
                    or fila["corrida"] != numero
                    or fila["hash_config"] != hash_esperado
                    or fila["hash_prompt"] != hash_prompt
                    or fila["serial"]
                    != identificador.split(":")[-1]
                ):
                    raise ValueError(
                        f"Registro inconsistente: "
                        f"{prefijo}/{identificador}"
                    )

                valido, _ = validar_prediccion(
                    fila["prediccion"]
                )

                if valido != fila["valido"]:
                    raise ValueError(
                        f"Validez inconsistente: "
                        f"{prefijo}/{identificador}"
                    )

                if (
                    fila.get("contexto_revisar")
                    or fila.get("salida_limitada")
                    or fila.get("done") is not True
                ):
                    raise ValueError(
                        f"Revisar inferencia: "
                        f"{prefijo}/{identificador}"
                    )

                for campo in (
                    "tiempo_s",
                    "prompt_eval_count",
                    "eval_count",
                ):
                    valor = fila.get(campo)

                    if (
                        not isinstance(valor, (int, float))
                        or isinstance(valor, bool)
                        or valor < 0
                    ):
                        raise ValueError(
                            f"Contador incorrecto: "
                            f"{campo}/{identificador}"
                        )

                if (
                    fila["prompt_eval_count"]
                    >= congelado["opciones"]["num_ctx"]
                    - congelado["opciones"]["num_predict"]
                ):
                    raise ValueError(
                        f"Presupuesto de contexto: "
                        f"{identificador}"
                    )

            if recurso["invalidos"] != sum(
                not f["valido"] for f in filas.values()
            ):
                raise ValueError(
                    f"Invalidos inconsistentes: {prefijo}"
                )

            corridas[numero] = filas
            recursos[numero] = recurso

        diferencias = Counter()
        ejemplos_diferencias = []

        for identificador in ids:
            firmas = [
                firma_prediccion(
                    corridas[n][identificador]
                )
                for n in (1, 2, 3)
            ]

            if len(set(firmas)) > 1:
                diferencias["clasificacion"] += 1

                if len(ejemplos_diferencias) < 10:
                    ejemplos_diferencias.append({
                        "event_id": identificador,
                        "predicciones": firmas,
                    })

            niveles = [
                f[1] for f in firmas
                if f[0] != "INVALIDA"
            ]

            if len(set(niveles)) > 1:
                diferencias["nivel"] += 1

            amenazas = [
                f[0] for f in firmas
                if f[0] != "INVALIDA"
            ]

            if len(set(amenazas)) > 1:
                diferencias["amenaza"] += 1

        pares = {}

        for a, b in ((1, 2), (1, 3), (2, 3)):
            iguales = sum(
                firma_prediccion(
                    corridas[a][identificador]
                )
                == firma_prediccion(
                    corridas[b][identificador]
                )
                for identificador in ids
            )

            pares[f"{a}-{b}"] = {
                "iguales": iguales,
                "porcentaje": 100 * iguales / 361,
            }

        datos_corridas = {}

        for numero in (1, 2, 3):
            filas = corridas[numero]

            tiempos = [
                filas[i]["tiempo_s"]
                for i in ids
            ]

            datos_corridas[str(numero)] = {
                "eventos": len(filas),
                "invalidos": sum(
                    not f["valido"]
                    for f in filas.values()
                ),
                "tiempo_medio_s":
                    statistics.mean(tiempos),
                "tiempo_total_s":
                    recursos[numero]["tiempo_ejecucion_s"],
                "ram_pico_mib":
                    recursos[numero]["ram_pico_rss_ollama_mib"],
                "tokens_entrada_max":
                    max(
                        filas[i]["prompt_eval_count"]
                        for i in ids
                    ),
                "tokens_salida_max":
                    max(
                        filas[i]["eval_count"]
                        for i in ids
                    ),
            }

        reporte["modelos"][modelo] = {
            "corridas": datos_corridas,
            "concordancia_pares": pares,
            "eventos_clasificacion_variable":
                diferencias["clasificacion"],
            "eventos_nivel_variable":
                diferencias["nivel"],
            "eventos_amenaza_variable":
                diferencias["amenaza"],
            "ejemplos_diferencias":
                ejemplos_diferencias,
        }

        print("\n" + "=" * 60)
        print("MODELO:", modelo)
        print("=" * 60)
        print("Corridas verificadas: 3")
        print("Eventos por corrida: 361")

        for numero, datos in datos_corridas.items():
            print(
                f"Corrida {numero}: "
                f"invalidos={datos['invalidos']} "
                f"tokens_max={datos['tokens_entrada_max']} "
                f"media={datos['tiempo_medio_s']:.4f}s"
            )

        print(
            "Eventos con clasificacion variable:",
            diferencias["clasificacion"]
        )
        print(
            "Eventos con nivel variable:",
            diferencias["nivel"]
        )
        print(
            "Eventos con amenaza variable:",
            diferencias["amenaza"]
        )

        for par, dato in pares.items():
            print(
                f"Concordancia {par}: "
                f"{dato['iguales']}/361 "
                f"({dato['porcentaje']:.2f}%)"
            )

    if SALIDA.exists():
        raise FileExistsError(
            "La auditoria ya existe: " + str(SALIDA)
        )

    with SALIDA.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            reporte,
            archivo,
            indent=2,
            ensure_ascii=False,
        )

    print("\n" + "=" * 60)
    print("AUDITORIA DE SEIS CORRIDAS: OK")
    print("Archivo:", SALIDA)


if __name__ == "__main__":
    main()

