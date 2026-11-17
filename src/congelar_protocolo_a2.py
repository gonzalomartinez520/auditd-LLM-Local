
import hashlib
import json
import subprocess
from pathlib import Path

from config_llm_a2 import (
    OPCIONES,
    ESQUEMA_RESPUESTA,
)
from prompts_llm import cargar_desarrollo
from prompts_fewshot_fijo import cargar_protocolo

BASE = Path(__file__).resolve().parent.parent

DESTINO = BASE / "docs/protocolo_test_a2.json"

COMPARACION = (
    BASE / "results/llm_dev/"
    "comparacion_prompts_dev.json"
)

FUENTES = [
    "src/config_llm_a2.py",
    "src/prompts_llm.py",
    "src/prompts_fewshot_fijo.py",
    "src/clasificador_regex.py",
    "src/clasificador_regex_multiclase.py",
]

GANADORES_ESPERADOS = {
    "qwen3:0.6b": "few_shot_fijo",
    "gemma3:1b": "few_shot_fijo",
}

IDS_ESPERADOS = [
    "1794757388.778:776",
    "1794759743.393:1619",
    "1794774470.010:11880",
]


def sha256_archivo(ruta):
    return hashlib.sha256(
        ruta.read_bytes()
    ).hexdigest()


def comando_git(*argumentos):
    resultado = subprocess.run(
        ["git", *argumentos],
        cwd=BASE,
        text=True,
        capture_output=True,
        check=True,
    )
    return resultado.stdout.strip()


def main():
    if DESTINO.exists():
        raise SystemExit(
            "ERROR: el protocolo ya fue congelado."
        )

    # Exigir que el codigo utilizado este publicado
    # en el historial local de Git y sin cambios.
    for nombre in FUENTES:
        comando_git(
            "ls-files",
            "--error-unmatch",
            nombre,
        )

    estado = comando_git(
        "status", "--porcelain", "--", *FUENTES
    )

    if estado:
        raise ValueError(
            "Existen cambios en los archivos "
            "del clasificador. Publicalos primero."
        )

    with COMPARACION.open(
        encoding="utf-8"
    ) as archivo:
        comparacion = json.load(archivo)

    if comparacion["ganadores"] != GANADORES_ESPERADOS:
        raise ValueError(
            "Los prompts ganadores no coinciden."
        )

    if comparacion["total_eventos"] != 148:
        raise ValueError(
            "La comparacion no utilizo 148 eventos."
        )

    desarrollo = cargar_desarrollo()
    protocolo, ejemplos = cargar_protocolo(
        desarrollo
    )

    if protocolo["ids_ejemplos"] != IDS_ESPERADOS:
        raise ValueError(
            "Los ejemplos fijos cambiaron."
        )

    fuentes_hash = {
        nombre: sha256_archivo(BASE / nombre)
        for nombre in FUENTES
    }

    ejemplos_hash = {
        evento["event_id"]: hashlib.sha256(
            evento["texto"].encode("utf-8")
        ).hexdigest()
        for evento in ejemplos
    }

    congelado = {
        "proyecto": "TP Final A2",
        "estado": "CONGELADO_ANTES_DE_TEST",
        "commit_fuente": comando_git(
            "rev-parse", "HEAD"
        ),
        "ollama_version": "0.40.16",
        "modelos": {
            "qwen3:0.6b": {
                "id": "7df6b6e09427",
                "prompt": "few_shot_fijo",
                "f1_dev_148": 0.4737,
            },
            "gemma3:1b": {
                "id": "97558784bdc9",
                "prompt": "few_shot_fijo",
                "f1_dev_148": 0.3234,
            },
        },
        "opciones": OPCIONES,
        "esquema_respuesta": ESQUEMA_RESPUESTA,
        "formato_entrada": "parser_propio_normalizado",
        "ejemplos": {
            "ids": protocolo["ids_ejemplos"],
            "sha256_textos": ejemplos_hash,
        },
        "protocolo_dev": {
            "eventos_comparados": 148,
            "sha256_archivo": sha256_archivo(
                BASE / "results/llm_dev/"
                "protocolo_fewshot_fijo.json"
            ),
        },
        "dataset_referencia": {
            "sha256_etiquetas": sha256_archivo(
                BASE / "data/processed/dataset/"
                "etiquetas_multiclase.csv"
            ),
        },
        "sha256_codigo": fuentes_hash,
        "evaluacion_test": {
            "eventos_esperados": 361,
            "corridas_por_clasificador": 3,
            "clasificadores": [
                "regex_multiclase",
                "qwen3:0.6b",
                "gemma3:1b",
            ],
            "seleccion_prompts": "f1_binario_dev",
        },
    }

    DESTINO.parent.mkdir(
        parents=True, exist_ok=True
    )

    with DESTINO.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            congelado,
            archivo,
            ensure_ascii=False,
            indent=2,
        )

    print("=" * 60)
    print("CONGELAMIENTO DEL PROTOCOLO A2")
    print("=" * 60)

    print(
        "Commit fuente:",
        congelado["commit_fuente"]
    )
    print("Modelos:", list(congelado["modelos"]))
    print("Prompt:", "few_shot_fijo")
    print("Ejemplos:", protocolo["ids_ejemplos"])
    print("Parametros:", OPCIONES)
    print("Test reservado:", 361)
    print("Corridas:", 3)
    print("Archivo:", DESTINO)

    print("\nPROTOCOLO CONGELADO: OK")


if __name__ == "__main__":
    main()

