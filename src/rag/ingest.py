"""Indexa todos los PDFs de data/pdfs/. Correr cada vez que cambien los PDFs.

Usa prepare_chunks.py (limpieza + chunking por secciones/requisitos) y después
calcula embeddings con BGE-M3 y guarda el índice FAISS.
"""
import json
import os
from types import SimpleNamespace

os.environ["HF_HUB_OFFLINE"] = "1"

import faiss
from sentence_transformers import SentenceTransformer

from src import config
from src.rag.prepare_chunks import process_pdf, write_report


def main():
    pdfs = sorted(config.PDFS_DIR.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No hay PDFs en {config.PDFS_DIR}")

    args = SimpleNamespace(
        max_tokens=config.MAX_TOKENS, min_tokens=config.MIN_TOKENS,
        flag_min=config.FLAG_MIN, overlap_sentences=config.OVERLAP_ORACIONES,
        seed=config.SEMILLA,
    )
    docs = []
    for pdf in pdfs:
        d = process_pdf(pdf, args)
        print(f"{pdf.name}: {len(d['chunks'])} fragmentos ({d['strategy']})")
        if not d["chunks"]:
            print("  AVISO: sin texto (¿PDF escaneado? requeriría OCR)")
        docs.append(d)

    crudos = [c for d in docs for c in d["chunks"]]
    if not crudos:
        raise SystemExit("Ningún PDF produjo fragmentos.")

    # Formato que consume agente.py. "texto" (con encabezado de sección) es lo que se embebe.
    todos = [{
        "id": c["id"],
        "archivo": c["doc"],
        "pagina": c["page_start"],
        "pagina_fin": c["page_end"],
        "texto": c["text"],
    } for c in crudos]

    emb = SentenceTransformer(config.MODELO_EMB, device="cpu")
    vec = emb.encode([c["texto"] for c in todos], normalize_embeddings=True,
                     show_progress_bar=True).astype("float32")

    idx = faiss.IndexFlatIP(vec.shape[1])
    idx.add(vec)
    config.INDICE.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(idx, str(config.INDICE))
    config.CHUNKS.write_text(json.dumps(todos, ensure_ascii=False), encoding="utf-8")
    write_report(config.REPORTE, docs, crudos, args)
    print(f"Índice listo: {len(todos)} fragmentos de {len(pdfs)} PDFs")
    print(f"Revisa la calidad del chunking en {config.REPORTE}")


if __name__ == "__main__":
    main()
