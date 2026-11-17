
import csv
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

DATA = BASE / "data/processed/dataset"
RESULTS = BASE / "results"

DEV = DATA / "desarrollo.jsonl"
ETIQUETAS = DATA / "etiquetas.csv"

SALIDA = RESULTS / "regex_dev_predicciones.csv"
RESUMEN = RESULTS / "regex_dev_resumen.json"

REGLAS = {
    "R1_SU": re.compile(
        r"(?m)^tipo=SYSCALL\b[^\n]*\bcomm=su(?:\s|$)"
    ),
    "R2_AUTH_FALLIDA": re.compile(
        r"(?m)^tipo=(?:USER_AUTH|USER_ERR)\b"
        r"[^\n]*\bres=(?:failed|no)(?:\s|$)",
        re.IGNORECASE,
    ),
}

PATRON_PROCESO = re.compile(
    r"(?:^|\s)comm=(\S+)"
)

PATRON_UID = re.compile(
    r"(?:^|\s)uid=(\S+)"
)

PATRON_EUID = re.compile(
    r"(?:^|\s)euid=(\S+)"
)

PATRON_SHADOW = re.compile(
    r"(?m)^tipo=PATH\b[^\n]*"
    r"\bruta=/etc/shadow(?:\s|$)"
)


def extraer(patron, texto):
    coincidencia = patron.search(texto)
    return coincidencia.group(1) if coincidencia else None


def detectar_reglas(texto):
    detectadas = []

    for nombre, patron in REGLAS.items():
        if patron.search(texto):
            detectadas.append(nombre)

    lineas_syscall = [
        linea
        for linea in texto.splitlines()
        if linea.startswith("tipo=SYSCALL")
    ]

    procesos = []

    for linea in lineas_syscall:
        proceso = extraer(PATRON_PROCESO, linea)
        uid = extraer(PATRON_UID, linea)
        euid = extraer(PATRON_EUID, linea)

        if proceso:
            procesos.append(proceso)

        # R3: servicio no privilegiado ejecutando
        # bash/id con privilegios efectivos de root.
        if (
            proceso in {"bash", "id"}
            and uid is not None
            and uid not in {"0", "root"}
            and euid in {"0", "root"}
        ):
            detectadas.append("R3_UID_EUID")

    # R4: proceso generico leyendo /etc/shadow.
    if (
        PATRON_SHADOW.search(texto)
        and any(p in {"cat", "cp"} for p in procesos)
    ):
        detectadas.append("R4_SHADOW_GENERICO")

    return sorted(set(detectadas))


def cargar_etiquetas():
    with ETIQUETAS.open(
        newline="", encoding="utf-8"
    ) as archivo:
        filas = list(csv.DictReader(archivo))

    etiquetas = {}

    for fila in filas:
        identificador = fila["event_id"]

        if identificador in etiquetas:
            raise ValueError(
                f"Etiqueta duplicada: {identificador}"
            )

        etiquetas[identificador] = fila

    return etiquetas


def calcular_metricas(filas):
    tp = sum(
        f["real"] == 1 and f["prediccion"] == 1
        for f in filas
    )
    tn = sum(
        f["real"] == 0 and f["prediccion"] == 0
        for f in filas
    )
    fp = sum(
        f["real"] == 0 and f["prediccion"] == 1
        for f in filas
    )
    fn = sum(
        f["real"] == 1 and f["prediccion"] == 0
        for f in filas
    )

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    accuracy = (tp + tn) / len(filas) if filas else 0.0

    return {
        "TP": tp,
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }


def main():
    if SALIDA.exists() or RESUMEN.exists():
        raise SystemExit(
            "ERROR: ya existen archivos de resultados. "
            "No se sobrescribiran."
        )

    if not DEV.is_file() or not ETIQUETAS.is_file():
        raise SystemExit(
            "ERROR: faltan archivos del dataset."
        )

    etiquetas = cargar_etiquetas()
    filas = []

    with DEV.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue

            evento = json.loads(linea)
            identificador = evento["event_id"]

            referencia = etiquetas.get(identificador)

            if referencia is None:
                raise ValueError(
                    f"Falta etiqueta para {identificador}"
                )

            texto = evento["texto"]
            reglas = detectar_reglas(texto)

            filas.append({
                "event_id": identificador,
                "fuente": referencia["fuente"],
                "real": int(referencia["amenaza"]),
                "prediccion": int(bool(reglas)),
                "reglas": ",".join(reglas),
            })

    if len(filas) != 158:
        raise ValueError(
            f"Dev deberia tener 158 eventos, "
            f"pero contiene {len(filas)}"
        )

    metricas = calcular_metricas(filas)

    por_fuente = {}

    for fuente in sorted({f["fuente"] for f in filas}):
        subconjunto = [
            f for f in filas if f["fuente"] == fuente
        ]

        por_fuente[fuente] = {
            "eventos": len(subconjunto),
            "detectados": sum(
                f["prediccion"] for f in subconjunto
            ),
            "metricas": calcular_metricas(subconjunto),
        }

    activaciones = Counter()

    for fila in filas:
        if fila["reglas"]:
            activaciones.update(
                fila["reglas"].split(",")
            )

    resumen = {
        "conjunto": "desarrollo",
        "eventos": len(filas),
        "reglas": list(REGLAS) + [
            "R3_UID_EUID",
            "R4_SHADOW_GENERICO",
        ],
        "metricas": metricas,
        "activaciones": dict(activaciones),
        "por_fuente": por_fuente,
    }

    RESULTS.mkdir(parents=True, exist_ok=True)

    with SALIDA.open(
        "x", newline="", encoding="utf-8"
    ) as archivo:
        writer = csv.DictWriter(
            archivo,
            fieldnames=[
                "event_id",
                "fuente",
                "real",
                "prediccion",
                "reglas",
            ],
        )
        writer.writeheader()
        writer.writerows(filas)

    with RESUMEN.open(
        "x", encoding="utf-8"
    ) as archivo:
        json.dump(
            resumen,
            archivo,
            indent=2,
            ensure_ascii=False,
        )

    print("=" * 55)
    print("CLASIFICADOR REGEX - DESARROLLO A2")
    print("=" * 55)

    print("Eventos evaluados:", len(filas))

    print("\nMATRIZ DE CONFUSION")
    print("TP:", metricas["TP"])
    print("TN:", metricas["TN"])
    print("FP:", metricas["FP"])
    print("FN:", metricas["FN"])

    print("\nMETRICAS")
    print(f'Precision: {metricas["precision"]:.4f}')
    print(f'Recall:    {metricas["recall"]:.4f}')
    print(f'F1:        {metricas["f1"]:.4f}')
    print(f'Accuracy:  {metricas["accuracy"]:.4f}')

    print("\nACTIVACIONES POR REGLA")
    for regla, cantidad in activaciones.most_common():
        print(f"{regla}: {cantidad}")

    print("\nDETECCIONES POR ESCENARIO")
    for fuente, info in por_fuente.items():
        print(
            f'{fuente:<15} '
            f'{info["detectados"]:>3} / '
            f'{info["eventos"]:>3}'
        )

    print("\nEVALUACION DEV: OK")
    print("Predicciones:", SALIDA)
    print("Resumen:", RESUMEN)


if __name__ == "__main__":
    main()

