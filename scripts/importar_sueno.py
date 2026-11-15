"""Convierte el dataset de actigrafía (BRSM, data/sleep/) a data/sueno.json.

Uso:  python scripts/importar_sueno.py [csv_entrada] [json_salida]

- Una noche por (tripulante, fecha): si hay varios registros de la misma noche se promedian
  y la medicación se junta en un solo texto.
- Latencia (h:mm) -> minutos; duración (h:mm) -> horas; eficiencia ya viene en %.
- Los sujetos del estudio se asignan a tripulantes con SUJETOS.
Salida: lista de {usuario, timestamp (YYYY-MM-DD), fase, medicacion, valores: {variable: número}}
ordenada por tripulante y fecha. Es idempotente.
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "data" / "sleep" / "BRSMACT_Campaign_1_Actigraphy" / "BRSMACT_Campagin_1_Actigraphy_Query_Result"
SALIDA = RAIZ / "data" / "sueno.json"

SUJETOS = {"C1G0003": "astro_1", "C1G0002": "astro_2"}   # sujeto del estudio -> tripulante


def minutos(txt):
    """'h:mm' (o '0') -> minutos."""
    txt = txt.strip()
    if ":" not in txt:
        return float(txt)
    h, m = txt.split(":")
    return int(h) * 60 + int(m)


def convertir(ruta=ENTRADA):
    noches = defaultdict(list)
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            usuario = SUJETOS.get(r["Subject"].strip())
            if not usuario:
                continue
            fecha = datetime.strptime(r["Date"].strip(), "%m/%d/%Y").date().isoformat()
            noches[(usuario, fecha)].append(r)
    salida = []
    for (usuario, fecha), regs in sorted(noches.items()):
        meds = sorted({r["Comments"].strip() for r in regs if r["Comments"].strip()})
        salida.append({
            "usuario": usuario, "timestamp": fecha, "fase": regs[0]["Test_Phase"].strip(),
            "medicacion": "; ".join(meds) or None,
            "valores": {
                "sueno_latencia": round(mean(minutos(r["Sleep latency"]) for r in regs), 1),
                "sueno_duracion": round(mean(minutos(r["Sleep duration"]) for r in regs) / 60, 2),
                "sueno_eficiencia": round(mean(float(r["Sleep efficiency"]) for r in regs), 1),
            },
        })
    return salida


if __name__ == "__main__":
    ent = Path(sys.argv[1]) if len(sys.argv) > 1 else ENTRADA
    sal = Path(sys.argv[2]) if len(sys.argv) > 2 else SALIDA
    datos = convertir(ent)
    sal.write_text(json.dumps(datos, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    por_u = defaultdict(int)
    for n in datos:
        por_u[n["usuario"]] += 1
    print(f"{len(datos)} noches -> {sal}  {dict(por_u)}")
