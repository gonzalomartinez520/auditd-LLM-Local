
import csv
import hashlib
import json
from collections import defaultdict, Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data/processed/dataset"
RESULTS = BASE / "results/analisis_final"

def leer_jsonl(ruta):
    with ruta.open(encoding="utf-8") as f:
        return [
            json.loads(linea)
            for linea in f if linea.strip()
        ]

with (DATA / "etiquetas_multiclase.csv").open(
    encoding="utf-8", newline=""
) as f:
    etiquetas = {
        fila["event_id"]: fila
        for fila in csv.DictReader(f)
    }

grupos = defaultdict(list)

for conjunto in ("desarrollo", "prueba"):
    eventos = leer_jsonl(DATA / f"{conjunto}.jsonl")

    for evento in eventos:
        eid = evento["event_id"]
        etiqueta = etiquetas[eid]
        huella = hashlib.sha256(
            evento["texto"].encode("utf-8")
        ).hexdigest()

        grupos[huella].append({
            "id": eid,
            "conjunto": conjunto,
            "fuente": etiqueta["fuente"],
            "nivel": etiqueta["nivel"],
            "amenaza": etiqueta["amenaza"],
        })

conflictos = []

for huella, eventos in grupos.items():
    niveles = {e["nivel"] for e in eventos}
    amenazas = {e["amenaza"] for e in eventos}

    if len(niveles) > 1 or len(amenazas) > 1:
        conflictos.append({
            "hash_texto": huella,
            "eventos": len(eventos),
            "fuentes": sorted({
                e["fuente"] for e in eventos
            }),
            "niveles": sorted(niveles),
            "amenazas": sorted(amenazas),
            "ejemplos": eventos[:6],
        })

with (RESULTS / "conflictos_etiquetas.json").open(
    "x", encoding="utf-8"
) as f:
    json.dump(
        conflictos, f,
        indent=2, ensure_ascii=False
    )

print("=" * 60)
print("CONFLICTOS ENTRE TEXTO Y ETIQUETAS")
print("=" * 60)
print("Patrones diferentes:", len(grupos))
print("Patrones con etiquetas conflictivas:", len(conflictos))
print(
    "Eventos asociados a patrones conflictivos:",
    sum(c["eventos"] for c in conflictos)
)

for conflicto in conflictos[:10]:
    print(
        "Fuentes:", conflicto["fuentes"],
        "Niveles:", conflicto["niveles"],
        "Eventos:", conflicto["eventos"]
    )

print("\n" + "=" * 60)
print("ERRORES BINARIOS POR CLASIFICADOR")
print("=" * 60)

with (RESULTS / "errores_test.csv").open(
    encoding="utf-8", newline=""
) as f:
    errores = list(csv.DictReader(f))

for modelo in (
    "regex_multiclase",
    "qwen3:0.6b",
    "gemma3:1b",
):
    seleccionados = [
        e for e in errores
        if e["modelo"] == modelo
        and e["corrida"] == "1"
    ]

    conteos = Counter(
        (e["fuente"], e["error"])
        for e in seleccionados
    )

    print("\nModelo:", modelo)
    print("Total errores:", len(seleccionados))

    for (fuente, error), cantidad in sorted(
        conteos.items()
    ):
        print(f"  {fuente}: {error}={cantidad}")

    print("Ejemplos:")
    for e in seleccionados[:5]:
        print(
            " ", e["event_id"],
            e["fuente"],
            e["error"],
            e["nivel_real"],
            "->",
            e["nivel_predicho"]
        )

print("\nANALISIS DE ERRORES: OK")

