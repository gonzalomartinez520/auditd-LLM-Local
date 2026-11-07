
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data/raw/normal"
OUTPUT_DIR = BASE_DIR / "data/processed"

RAW_FILE = DATA_DIR / "audit.log"

INTERVALS = [
    {
        "name": "primera_captura",
        "start": DATA_DIR / "inicio.txt",
        "end": DATA_DIR / "fin.txt",
    },
    {
        "name": "segunda_captura",
        "start": DATA_DIR / "inicio_extra.txt",
        "end": DATA_DIR / "fin_extra.txt",
    },
]

OUTPUT_FILE = OUTPUT_DIR / "normal_eventos_limpios.jsonl"
SUMMARY_FILE = OUTPUT_DIR / "normal_resumen_limpio.json"

AUDIT_PATTERN = re.compile(r"msg=audit\((\d+(?:\.\d+)?):(\d+)\)")
TYPE_PATTERN = re.compile(r"^type=([A-Z_]+)")
KEY_PATTERN = re.compile(r'\skey=(?:"[^"]*"|\S+)')
PROCTITLE_PATTERN = re.compile(r"proctitle=([0-9A-Fa-f]+)")

CONTROL_FILES = {
    "inicio.txt",
    "fin.txt",
    "inicio_extra.txt",
    "fin_extra.txt",
}


def read_timestamp(path):
    return datetime.fromisoformat(
        path.read_text(encoding="utf-8").strip()
    ).timestamp()


def exclusion_reason(records):
    for record in records:
        if (
            'a0="date"' in record
            and 'a1="--iso-8601=seconds"' in record
        ):
            return "comando_date_de_captura"

        match = re.search(r'a0="tee"\s+a1="([^"]+)"', record)

        if match and Path(match.group(1)).name in CONTROL_FILES:
            return "comando_tee_de_captura"

    return None


def clean_record(record):
    # Eliminar la clave de auditoría.
    record = KEY_PATTERN.sub("", record)

    # Decodificar PROCTITLE hexadecimal.
    match = PROCTITLE_PATTERN.search(record)

    if match:
        try:
            decoded = bytes.fromhex(match.group(1)).decode(
                "utf-8", errors="replace"
            )
            arguments = decoded.split("\x00")
            decoded = " ".join(arg for arg in arguments if arg)

            replacement = (
                "proctitle_decoded="
                + json.dumps(decoded, ensure_ascii=False)
            )

            record = record[:match.start()] + replacement + record[match.end():]

        except ValueError:
            pass

    return record


def main():
    intervals = []

    for interval in INTERVALS:
        intervals.append({
            "name": interval["name"],
            "start": read_timestamp(interval["start"]),
            "end": read_timestamp(interval["end"]),
            "events": set(),
            "lines": 0,
        })

    events = {}
    total_lines = 0
    lines_without_id = 0
    lines_outside = 0

    with RAW_FILE.open(
        "r", encoding="utf-8", errors="replace"
    ) as file:
        for line in file:
            total_lines += 1
            match = AUDIT_PATTERN.search(line)

            if not match:
                lines_without_id += 1
                continue

            timestamp, serial = match.groups()
            timestamp_value = float(timestamp)

            interval = next(
                (
                    item for item in intervals
                    if item["start"] <= timestamp_value <= item["end"]
                ),
                None,
            )

            if interval is None:
                lines_outside += 1
                continue

            event_id = f"{timestamp}:{serial}"

            if event_id not in events:
                events[event_id] = {
                    "event_id": event_id,
                    "timestamp": timestamp_value,
                    "intervalo": interval["name"],
                    "records": set(),
                }

            events[event_id]["records"].add(line.rstrip("\n"))
            interval["events"].add(event_id)
            interval["lines"] += 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    type_counts = Counter()
    interval_counts = Counter()
    excluded_counts = Counter()
    events_with_syscall = 0
    excluded_events = 0

    with OUTPUT_FILE.open("w", encoding="utf-8") as output:
        for event_id in sorted(
            events, key=lambda x: events[x]["timestamp"]
        ):
            event_data = events[event_id]
            original_records = sorted(event_data["records"])

            reason = exclusion_reason(original_records)

            if reason:
                excluded_events += 1
                excluded_counts[reason] += 1
                continue

            records = [
                clean_record(record)
                for record in original_records
            ]

            record_types = []

            for record in records:
                match = TYPE_PATTERN.match(record)

                if match:
                    record_types.append(match.group(1))

            type_counts.update(record_types)
            interval_counts[event_data["intervalo"]] += 1

            has_syscall = "SYSCALL" in record_types

            if has_syscall:
                events_with_syscall += 1

            event = {
                "event_id": event_id,
                "intervalo": event_data["intervalo"],
                "record_types": record_types,
                "has_syscall": has_syscall,
                "records": records,
            }

            output.write(
                json.dumps(event, ensure_ascii=False) + "\n"
            )

    summary = {
        "archivo_origen": str(RAW_FILE.relative_to(BASE_DIR)),
        "lineas_totales": total_lines,
        "lineas_sin_identificador": lines_without_id,
        "lineas_fuera_de_intervalos": lines_outside,
        "eventos_unicos_capturados": len(events),
        "eventos_excluidos": excluded_events,
        "motivos_exclusion": dict(excluded_counts),
        "eventos_limpios": len(events) - excluded_events,
        "eventos_con_syscall": events_with_syscall,
        "eventos_por_captura": {
            item["name"]: len(item["events"])
            for item in intervals
        },
        "eventos_limpios_por_captura": dict(interval_counts),
        "lineas_por_captura": {
            item["name"]: item["lines"]
            for item in intervals
        },
        "tipos_de_registro": dict(type_counts),
    }

    SUMMARY_FILE.write_text(
        json.dumps(summary, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=4, ensure_ascii=False))
    print(f"\nEventos limpios: {OUTPUT_FILE}")
    print(f"Resumen: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()

