#!/usr/bin/env python3
"""
prepare_chunks.py - Limpieza y chunking de PDFs para un RAG local / offline.

Que hace (en orden):
  1. Extrae el texto de cada pagina (pypdf, puro Python) conservando el numero de pagina.
  2. Limpia: quita paginas de indice / historial, encabezados y pies repetidos,
     guiones de fin de linea, ligaduras, saltos de linea dentro de un parrafo y
     errores tipicos de OCR (lista editable en PROFILES).
  3. Parte en chunks:
       - Estandares con requisitos "[V1 4011]": un chunk por requisito (+ su Rationale),
         con seccion e ID en el encabezado del chunk.
       - Resto de documentos: por secciones/etiquetas, y si una seccion es larga,
         ventanas de oraciones con traslape.
  4. Guarda chunks.jsonl (+ metadatos) y report.md para revisar ANTES de calcular embeddings.

No calcula embeddings ni llama a ningun modelo. No usa internet.
Dependencia unica: pypdf  (pip install pypdf)

Uso:
  python prepare_chunks.py --pdf-dir ./pdfs --out ./chunks_out
  python prepare_chunks.py --pdfs a.pdf b.pdf --max-tokens 350 --min-tokens 60

Nota sobre tokens: sin tokenizer se estiman como palabras * 1.3 (ingles). Es solo una
aproximacion para dimensionar chunks; si usas un modelo de embeddings con su tokenizer,
reemplaza est_tokens().
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

# --------------------------------------------------------------------------------------
# Perfiles por documento (editables). Se elige el primero cuyo "match" aparece en el
# nombre del archivo (sin importar mayusculas). Un PDF sin perfil usa la estrategia
# generica con el titulo del PDF (o el nombre del archivo).
# --------------------------------------------------------------------------------------
PROFILES: list[dict] = [
    {
        "match": r"nasa[-_ ]?2|nasa-std",
        "slug": "nasa-std-3001-v1",
        "title": "NASA-STD-3001 Vol. 1 Rev. C (Crew Health)",
        "strategy": "standard",
        # Paginas que se descartan si su texto contiene alguna de estas expresiones
        "skip_page_regex": [r"DOCUMENT HISTORY LOG", r"Editorial changes throughout document"],
        # Se omiten las paginas desde la que EMPIEZA el Apendice D (plantilla en blanco de
        # cumplimiento que solo duplica los requisitos) hasta que empieza el Apendice E.
        "skip_between": (r"(?m)^APPENDIX D\b", r"(?m)^APPENDIX E\b"),
        # Tablas de espectros en notacion cientifica (1.338E-02 ...): ruido para un RAG.
        "strip_sci_tables": True,
    },
    {
        "match": r"techport",
        "slug": "techport-18874-amp",
        "title": "NASA TechPort 18874 - Assisted Medical Procedures (AMP)",
        "strategy": "generic",
        # Lineas que son un encabezado de seccion por si solas
        "heading_lines": [
            "Project Description", "Anticipated Benefits", "Organizational Responsibility",
            "Project Duration", "Partner Organizations", "Project Contacts",
            "Primary U.S. Work Locations", "Technology Area", "Technology Maturity",
            "Technology Outcomes", "Project Library Stories", "Project Library Links",
            "Target Destinations",
        ],
        "drop_numeric_lines": True,  # escala TRL "1 2 3 4 5 6 7 8 9" y similares
    },
    {
        "match": r"nasa[-_ ]?1",
        "slug": "nasa-jsc-2003-iss-checklist",
        "title": "NASA JSC 2003 abstract - Human factors evaluation of the ISS Emergency Medical Checklist",
        "strategy": "generic",
        # Etiquetas dentro del texto que inician una seccion (se conserva el texto)
        "label_regex": r"^(Introduction|Method|Results|Conclusions?):",
        "drop_lone_letters": True,  # basura de OCR (una "J" suelta)
        # Correcciones de OCR (regex -> reemplazo). Solo las que son seguras.
        "ocr_fixes": [
            (r"\bNation al\b", "National"),
            (r"BJohn\s*son", "B. Johnson"),
            (r"\bNSBRl\b", "NSBRI"),
            (r"\[mal\b", "final"),
            (r"\s+([,.;:])(?=\s|$)", r"\1"),  # "problems ." -> "problems."
        ],
    },
]

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬀ": "ff"}
TERMINAL = (".", ":", ";", "!", "?", "]")
ABBREVIATIONS = ("e.g.", "i.e.", "et al.", "vs.", "No.", "Fig.", "Figs.", "Eq.", "Vol.",
                 "approx.", "etc.", "U.S.", "Dr.", "St.")

REQ_RE = re.compile(r"^\[V1\s*(\d{4})\]")
RAT_RE = re.compile(r"^\[Rationale\b", re.I)
HEAD_RE = re.compile(
    r"^(?P<num>\d+(?:\.\d+)+|[A-Z]\.\d+(?:\.\d+)*|\d{1,2}\.)\s+(?P<title>\S.*)$"
)
APPENDIX_RE = re.compile(r"^APPENDIX\s+([A-Z])\b\s*(.*)$")


# --------------------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------------------
def est_tokens(text: str) -> int:
    """Estimacion de tokens (palabras * 1.3). Reemplazar por el tokenizer real si se quiere."""
    return math.ceil(len(text.split()) * 1.3)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "doc"


def pick_profile(filename: str) -> dict:
    for prof in PROFILES:
        if re.search(prof["match"], filename, re.I):
            return prof
    return {}


def normalize_text(text: str, ocr_fixes: list[tuple[str, str]]) -> str:
    text = text.replace("\r", "")
    for k, v in LIGATURES.items():
        text = text.replace(k, v)
    text = text.replace("­\n", "").replace("­", "")  # guion suave
    text = text.replace(" ", " ")
    for pat, rep in ocr_fixes:
        text = re.sub(pat, rep, text)
    return text


def reflow(lines: list[str]) -> str:
    """Une las lineas de un parrafo. Si una linea termina en '-' y la siguiente sigue con
    una letra/numero, se pega conservando el guion (pre-\\nmission -> pre-mission), porque en
    estos documentos casi todos los guiones de fin de linea son de palabras compuestas."""
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not out:
            out = ln
        elif out.endswith("-") and ln[:1].isalnum() and out[-2:-1].isalnum():
            out += ln
        else:
            out += " " + ln
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[(\"“])", text)
    merged: list[str] = []
    for p in parts:
        if merged and merged[-1].endswith(ABBREVIATIONS):
            merged[-1] += " " + p
        else:
            merged.append(p)
    return [m for m in merged if m.strip()]


def hard_split(sentence: str, max_tokens: int) -> list[str]:
    words = sentence.split()
    step = max(1, int(max_tokens / 1.3))
    return [" ".join(words[i:i + step]) for i in range(0, len(words), step)]


def window_sentences(text: str, max_tokens: int, overlap: int) -> list[str]:
    sents: list[str] = []
    for s in split_sentences(text):
        sents.extend(hard_split(s, max_tokens) if est_tokens(s) > max_tokens else [s])
    out: list[str] = []
    i = 0
    while i < len(sents):
        j, tok = i, 0
        while j < len(sents) and (j == i or tok + est_tokens(sents[j]) <= max_tokens):
            tok += est_tokens(sents[j])
            j += 1
        out.append(" ".join(sents[i:j]))
        if j >= len(sents):
            break
        i = max(j - overlap, i + 1)
    return out


# --------------------------------------------------------------------------------------
# Estructuras
# --------------------------------------------------------------------------------------
@dataclass
class Para:
    text: str
    page_start: int
    page_end: int
    forced: str | None = None  # "heading" cuando viene de heading_lines


@dataclass
class Unit:
    section_num: str = ""
    section_title: str = ""
    req_ids: list[str] = field(default_factory=list)
    paras: list[Para] = field(default_factory=list)
    is_req: bool = False

    @property
    def tokens(self) -> int:
        return sum(est_tokens(p.text) for p in self.paras)

    @property
    def label(self) -> str:
        if self.section_num and self.section_title:
            return f"§{self.section_num} {self.section_title}"
        return self.section_title or (f"§{self.section_num}" if self.section_num else "")

    def merged_with(self, other: "Unit") -> "Unit":
        return Unit(
            section_num=self.section_num,
            section_title=self.section_title,
            req_ids=self.req_ids + other.req_ids,
            paras=self.paras + other.paras,
            is_req=self.is_req or other.is_req,
        )


# --------------------------------------------------------------------------------------
# Paso 1-2: extraccion y limpieza
# --------------------------------------------------------------------------------------
def read_pdf(path: Path) -> tuple[list[tuple[int, str]], str]:
    reader = PdfReader(str(path))
    title = ""
    try:
        title = (reader.metadata.title or "").strip() if reader.metadata else ""
    except Exception:
        pass
    pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
    return pages, title


def detect_boilerplate(pages: list[tuple[int, str]], edge: int = 3, ratio: float = 0.4) -> set[str]:
    """Lineas (con digitos normalizados) que se repiten en el borde superior/inferior de
    >= 40% de las paginas: encabezados y pies como 'NASA-STD-3001... / 37 of 86'."""
    if len(pages) < 5:
        return set()
    norm = lambda s: re.sub(r"\d+", "#", s.strip())
    counts: Counter = Counter()
    for _, text in pages:
        lines = [l for l in text.split("\n") if l.strip()]
        for l in set(lines[:edge] + lines[-edge:]):
            counts[norm(l)] += 1
    return {k for k, v in counts.items() if v >= ratio * len(pages)}


def page_skip_reason(text: str, skip_regex: list[str]) -> str | None:
    lines = [l for l in text.split("\n") if l.strip()]
    if lines:
        dots = sum(1 for l in lines if re.search(r"\.{5,}", l))
        if dots / len(lines) > 0.12:
            return "indice / lista de figuras o tablas (puntos guia)"
    for pat in skip_regex:
        if re.search(pat, text):
            return f"coincide con skip_page_regex: {pat}"
    if not text.strip():
        return "pagina sin texto (posible imagen escaneada: requiere OCR)"
    return None


def build_paragraphs(pages, prof, boiler, report) -> list[Para]:
    skip_regex = prof.get("skip_page_regex", [])
    ocr_fixes = prof.get("ocr_fixes", [])
    heading_lines = set(prof.get("heading_lines", []))
    label_re = re.compile(prof["label_regex"]) if prof.get("label_regex") else None
    norm = lambda s: re.sub(r"\d+", "#", s.strip())

    skip_between = prof.get("skip_between")
    in_skip_block = False
    split_headings = prof.get("strategy") == "standard"

    paras: list[Para] = []
    for page_no, raw in pages:
        reason = page_skip_reason(raw, skip_regex)
        if reason is None and skip_between:
            start_re, end_re = skip_between
            if not in_skip_block and re.search(start_re, raw):
                in_skip_block = True
            elif in_skip_block and re.search(end_re, raw):
                in_skip_block = False
            if in_skip_block:
                reason = f"bloque omitido (skip_between): {start_re} ... {end_re}"
        if reason:
            report["skipped_pages"].append((page_no, reason))
            continue
        norm_text = normalize_text(raw, ocr_fixes)
        if prof.get("strip_sci_tables"):
            norm_text, n_sub = re.subn(r"(?:\b\d\.\d{3}E[+-]\d{2}\b[ \t]*\n?[ \t]*){6,}",
                                       "[tabla numerica omitida] ", norm_text)
            report["sci_tables_stripped"] += n_sub
        lines = norm_text.split("\n")

        # Quitar encabezados/pies repetidos (solo en los bordes de la pagina)
        idx = [i for i, l in enumerate(lines) if l.strip()]
        edge_idx = set(idx[:3] + idx[-3:])
        kept = []
        for i, l in enumerate(lines):
            if i in edge_idx and norm(l) in boiler:
                report["boilerplate_removed"][norm(l)] += 1
                continue
            kept.append(l)

        cur: list[str] = []

        def flush():
            if not cur:
                return
            # Un encabezado pegado a su texto (sin linea en blanco): "2.2 Government Documents\nNASA..."
            if (split_headings and len(cur) >= 3 and classify(cur[0].strip())[0] == "head"
                    and classify(reflow(cur))[0] != "head"):
                paras.append(Para(reflow(cur[:1]), page_no, page_no))
                paras.append(Para(reflow(cur[1:]), page_no, page_no))
            else:
                paras.append(Para(reflow(cur), page_no, page_no))
            cur.clear()

        for ln in kept:
            s = ln.strip()
            if not s:
                flush()
                continue
            if prof.get("drop_numeric_lines") and re.fullmatch(r"[\d\s.,]+", s):
                continue
            if prof.get("drop_lone_letters") and re.fullmatch(r"[A-Za-z]", s):
                continue
            if s in heading_lines:
                flush()
                paras.append(Para(s, page_no, page_no, forced="heading"))
                continue
            if label_re and label_re.match(s):
                flush()
            cur.append(s)
        flush()

    if prof.get("strip_sci_tables"):
        # Encabezados de tabla repetidos por columnas: "Energy Proton Fluence" x5 -> x1
        for p in paras:
            p.text = re.sub(r"((?:\S+\s+){1,5}?)\1{2,}", r"\1", p.text)
    return join_across_pages(paras)


def classify(text: str) -> tuple:
    """('req', id) | ('rat',) | ('head', num, title) | ('body',)  -- solo para estandares."""
    m = REQ_RE.match(text)
    if m:
        return ("req", m.group(1))
    if RAT_RE.match(text):
        return ("rat",)
    m = APPENDIX_RE.match(text)
    if m and len(text) < 80:
        return ("head", f"Appendix {m.group(1)}", m.group(2).strip())
    m = HEAD_RE.match(text)
    if m and not text.endswith((".", ";", ":", ",")):
        num, title = m.group("num"), m.group("title")
        first = num.rstrip(".").split(".")[0]
        words = title.split()
        padded = f" {title.lower()} "
        sentence_like = any(w in padded for w in (" shall ", " may ", " must ", " is ", " are ",
                                                  " be ", " will ", " should ", " can "))
        ok = (
            len(title) >= 4 and len(words) <= 14 and len(text) <= 110
            and title[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZ(" and not sentence_like
        )
        if first.isdigit():
            ok = ok and 1 <= int(first) <= 12
            if num.endswith("."):  # "3. HEALTH AND MEDICAL CARE": solo si esta en mayusculas
                ok = ok and title.upper() == title
            elif len(title) < 6:
                ok = False  # evita valores como "0.6 Sv"
        if ok:
            return ("head", num.rstrip("."), title.strip())
    return ("body",)


def join_across_pages(paras: list[Para]) -> list[Para]:
    """Une un parrafo cortado por un salto de pagina con su continuacion."""
    out: list[Para] = []
    for p in paras:
        if out:
            prev = out[-1]
            joinable = (
                p.page_start != prev.page_end
                and prev.forced is None and p.forced is None
                and classify(prev.text)[0] in ("body", "req", "rat")
                and classify(p.text)[0] == "body"
            )
            open_rationale = RAT_RE.match(prev.text) and not prev.text.rstrip().endswith("]")
            if joinable and (not prev.text.rstrip().endswith(TERMINAL) or p.text[:1].islower() or open_rationale):
                prev.text = reflow([prev.text, p.text])
                prev.page_end = p.page_end
                continue
        out.append(p)
    return out


# --------------------------------------------------------------------------------------
# Paso 3: unidades y chunks
# --------------------------------------------------------------------------------------
def units_standard(paras: list[Para], report) -> list[Unit]:
    units: list[Unit] = []
    cur = Unit(section_title="Front matter")
    seen_ids: set[str] = set()
    appendix_title_pending = False
    for p in paras:
        kind = classify(p.text)
        if kind[0] == "req" and kind[1] in seen_ids:
            kind = ("body",)  # referencia a un requisito ya definido, no una definicion nueva
        if appendix_title_pending:
            appendix_title_pending = False
            if kind[0] == "body" and p.text.isupper() and len(p.text) < 80:
                cur.section_title = p.text.title() if not cur.section_title else cur.section_title
                report["outline"][-1] = (report["outline"][-1][0], cur.section_title, report["outline"][-1][2])
                continue
        if kind[0] == "head":
            units.append(cur)
            cur = Unit(section_num=kind[1], section_title=kind[2])
            report["outline"].append((kind[1], kind[2], p.page_start))
            appendix_title_pending = kind[1].startswith("Appendix") and not kind[2]
        elif kind[0] == "req":
            units.append(cur)
            seen_ids.add(kind[1])
            cur = Unit(section_num=cur.section_num, section_title=cur.section_title,
                       req_ids=[f"V1 {kind[1]}"], is_req=True)
            cur.paras.append(p)
            report["req_ids"].append(f"V1 {kind[1]}")
        else:
            cur.paras.append(p)
    units.append(cur)
    # Unidades triviales (solo un titulo, o un "None") no aportan a la busqueda
    kept = []
    for u in units:
        words = sum(len(p.text.split()) for p in u.paras)
        if not u.paras:
            continue
        if words < 5 and not u.is_req:
            report["dropped_units"].append(f"{u.label}: {' '.join(p.text for p in u.paras)}")
            continue
        kept.append(u)
    return kept


def units_generic(paras: list[Para], prof: dict) -> list[Unit]:
    label_re = re.compile(prof["label_regex"]) if prof.get("label_regex") else None
    units: list[Unit] = []
    cur = Unit(section_title="")
    for p in paras:
        if p.forced == "heading":
            units.append(cur)
            cur = Unit(section_title=p.text)
            continue
        m = label_re.match(p.text) if label_re else None
        if m:
            units.append(cur)
            cur = Unit(section_title=m.group(1))
        cur.paras.append(p)
    units.append(cur)
    return [u for u in units if u.paras]


def merge_small(units: list[Unit], min_tokens: int, max_tokens: int, same_section_only: bool) -> list[Unit]:
    out: list[Unit] = []
    i = 0
    while i < len(units):
        u = units[i]
        while (
            not u.is_req and u.tokens < min_tokens and i + 1 < len(units)
            and not units[i + 1].is_req
            and u.tokens + units[i + 1].tokens <= max_tokens
            and (not same_section_only or (units[i + 1].section_num, units[i + 1].section_title)
                 == (u.section_num, u.section_title))
        ):
            nxt = units[i + 1]
            merged = u.merged_with(nxt)
            if nxt.section_title and nxt.section_title != u.section_title:
                merged.section_title = f"{u.section_title} / {nxt.section_title}".strip(" /")
            u = merged
            i += 1
        out.append(u)
        i += 1
    return out


def pack_paragraphs(paras: list[Para], max_tokens: int, overlap: int) -> list[tuple[str, int, int]]:
    pieces: list[tuple[str, int, int]] = []
    buf: list[Para] = []
    buf_tok = 0

    def flush():
        nonlocal buf, buf_tok
        if buf:
            pieces.append(("\n\n".join(p.text for p in buf), buf[0].page_start, buf[-1].page_end))
        buf, buf_tok = [], 0

    for p in paras:
        t = est_tokens(p.text)
        if t > max_tokens:
            flush()
            for w in window_sentences(p.text, max_tokens, overlap):
                pieces.append((w, p.page_start, p.page_end))
            continue
        if buf and buf_tok + t > max_tokens:
            flush()
        buf.append(p)
        buf_tok += t
    flush()
    return pieces


def make_chunks(units: list[Unit], doc_title: str, slug: str, filename: str, strategy: str,
                max_tokens: int, overlap: int) -> list[dict]:
    chunks: list[dict] = []
    for u in units:
        pieces = pack_paragraphs(u.paras, max_tokens, overlap)
        for k, (body, p0, p1) in enumerate(pieces, 1):
            header_parts = [doc_title, u.label, ", ".join(u.req_ids)]
            if len(pieces) > 1:
                header_parts.append(f"parte {k}/{len(pieces)}")
            header = "[" + " | ".join(h for h in header_parts if h) + "]"
            text = f"{header}\n{body}"
            chunks.append({
                "id": f"{slug}-{len(chunks) + 1:04d}",
                "doc": filename,
                "doc_title": doc_title,
                "strategy": strategy,
                "section_num": u.section_num,
                "section_title": u.section_title,
                "req_ids": u.req_ids,
                "page_start": p0,
                "page_end": p1,
                "part": f"{k}/{len(pieces)}",
                "tokens_est": est_tokens(text),
                "body": body,
                "text": text,  # <- lo que se embebe y se le pasa al LLM
            })
    return chunks


# --------------------------------------------------------------------------------------
# Reporte
# --------------------------------------------------------------------------------------
def flag_chunk(c: dict, min_flag: int, max_tokens: int) -> list[str]:
    flags = []
    body = c["body"]
    if re.search(r"\.{5,}", body):
        flags.append("puntos guia (indice)")
    if c["tokens_est"] < min_flag and not c["req_ids"]:
        flags.append("muy corto")
    if c["tokens_est"] > max_tokens * 1.25:
        flags.append("muy largo")
    visible = re.sub(r"\s", "", body)
    if visible and sum(ch.isalpha() for ch in visible) / len(visible) < 0.6:
        flags.append("tabla o ruido (pocas letras)")
    if re.search(r"NASA-STD-3001, VOLUME|\b\d+ of \d+\b", body):
        flags.append("encabezado/pie residual")
    return flags


def write_report(path: Path, docs: list[dict], all_chunks: list[dict], args) -> None:
    rnd = random.Random(args.seed)
    L: list[str] = ["# Reporte de chunking\n"]
    L.append(f"Parametros: max_tokens={args.max_tokens}, min_tokens={args.min_tokens}, "
             f"overlap_sentences={args.overlap_sentences} (tokens estimados = palabras x 1.3)\n")

    L.append("## Resumen por documento\n")
    L.append("| Documento | Paginas usadas / total | Chunks | Tokens min / prom / max |")
    L.append("|---|---|---|---|")
    for d in docs:
        t = [c["tokens_est"] for c in d["chunks"]] or [0]
        L.append(f"| {d['title']} | {d['pages_total'] - len(d['report']['skipped_pages'])} / {d['pages_total']} "
                 f"| {len(d['chunks'])} | {min(t)} / {int(statistics.mean(t))} / {max(t)} |")
    total = sum(len(d["chunks"]) for d in docs)
    L.append(f"\nTotal: **{total} chunks**.\n")

    for d in docs:
        r = d["report"]
        L.append(f"## {d['title']}\n")
        L.append(f"Archivo: `{d['filename']}` - estrategia: `{d['strategy']}`\n")
        if r["skipped_pages"]:
            L.append("**Paginas omitidas:** " + "; ".join(f"p.{p} ({why})" for p, why in r["skipped_pages"]) + "\n")
        if r["boilerplate_removed"]:
            L.append("**Encabezados/pies removidos:** " +
                     "; ".join(f"`{k}` x{v}" for k, v in r["boilerplate_removed"].most_common(5)) + "\n")
        if r["sci_tables_stripped"]:
            L.append(f"**Tablas en notacion cientifica omitidas:** {r['sci_tables_stripped']}\n")
        if r["dropped_units"]:
            L.append("**Unidades triviales descartadas:** " + "; ".join(r["dropped_units"]) + "\n")
        if r["req_ids"]:
            ids = r["req_ids"]
            dup = [k for k, v in Counter(ids).items() if v > 1]
            L.append(f"**Requisitos detectados:** {len(ids)} ({len(set(ids))} unicos)"
                     + (f"; REPETIDOS: {', '.join(dup)}" if dup else "") + "\n")
            L.append("IDs: " + ", ".join(i.replace("V1 ", "") for i in ids) + "\n")
        if r["outline"]:
            L.append("**Esquema de secciones detectado** (revisalo: si falta o sobra algun encabezado, "
                     "ajusta HEAD_RE/classify):\n")
            L.append("```")
            for num, title, pg in r["outline"]:
                depth = num.count(".") if num[:8] != "Appendix" else 0
                L.append(f"{'  ' * depth}{num} {title}  (p.{pg})")
            L.append("```\n")

    flagged = [(c, f) for c in all_chunks if (f := flag_chunk(c, args.flag_min, args.max_tokens))]
    L.append(f"## Chunks marcados para revisar ({len(flagged)})\n")
    for c, f in flagged[:50]:
        L.append(f"- `{c['id']}` p.{c['page_start']}-{c['page_end']} ~{c['tokens_est']} tok: {', '.join(f)} "
                 f"- {c['body'][:90].replace(chr(10), ' ')}...")
    if len(flagged) > 50:
        L.append(f"- ... y {len(flagged) - 50} mas")
    L.append("")

    L.append("## Muestras aleatorias (3 por documento)\n")
    for d in docs:
        if not d["chunks"]:
            continue
        L.append(f"### {d['title']}\n")
        for c in rnd.sample(d["chunks"], min(3, len(d["chunks"]))):
            L.append(f"`{c['id']}` - p.{c['page_start']}-{c['page_end']} - ~{c['tokens_est']} tokens\n")
            L.append("```")
            L.append(c["text"][:900] + ("..." if len(c["text"]) > 900 else ""))
            L.append("```\n")
    path.write_text("\n".join(L), encoding="utf-8")


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def process_pdf(path: Path, args) -> dict:
    prof = pick_profile(path.name)
    pages, pdf_title = read_pdf(path)
    report = {"skipped_pages": [], "boilerplate_removed": Counter(), "outline": [], "req_ids": [],
              "dropped_units": [], "sci_tables_stripped": 0}
    boiler = detect_boilerplate(pages)
    paras = build_paragraphs(pages, prof, boiler, report)

    strategy = prof.get("strategy")
    if strategy is None:  # PDF sin perfil: autodeteccion
        n_req = sum(len(re.findall(r"\[V1\s*\d{4}\]", p.text)) for p in paras)
        strategy = "standard" if n_req >= 10 else "generic"
    title = prof.get("title") or pdf_title or path.stem
    slug = prof.get("slug") or slugify(title)

    units = units_standard(paras, report) if strategy == "standard" else units_generic(paras, prof)
    units = merge_small(units, args.min_tokens, args.max_tokens, same_section_only=(strategy == "standard"))
    chunks = make_chunks(units, title, slug, path.name, strategy, args.max_tokens, args.overlap_sentences)
    return {"title": title, "filename": path.name, "strategy": strategy, "pages_total": len(pages),
            "chunks": chunks, "report": report}


def main() -> int:
    ap = argparse.ArgumentParser(description="Limpieza y chunking de PDFs para RAG local")
    ap.add_argument("--pdf-dir", type=Path, help="carpeta con PDFs")
    ap.add_argument("--pdfs", nargs="*", type=Path, default=[], help="PDFs individuales")
    ap.add_argument("--out", type=Path, default=Path("chunks_out"))
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--min-tokens", type=int, default=60, help="unidades menores se unen con la siguiente")
    ap.add_argument("--flag-min", type=int, default=25, help="chunks menores a esto se marcan en el reporte")
    ap.add_argument("--overlap-sentences", type=int, default=1)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    pdfs = list(args.pdfs)
    if args.pdf_dir:
        pdfs += sorted(args.pdf_dir.glob("*.pdf"))
    if not pdfs:
        ap.error("indica --pdf-dir o --pdfs")

    args.out.mkdir(parents=True, exist_ok=True)
    docs = [process_pdf(p, args) for p in pdfs]
    all_chunks = [c for d in docs for c in d["chunks"]]

    with (args.out / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    write_report(args.out / "report.md", docs, all_chunks, args)

    for d in docs:
        t = [c["tokens_est"] for c in d["chunks"]] or [0]
        print(f"{d['filename']}: {len(d['chunks'])} chunks (~{min(t)}-{max(t)} tok), "
              f"{len(d['report']['skipped_pages'])} paginas omitidas")
    print(f"Total: {len(all_chunks)} chunks -> {args.out / 'chunks.jsonl'} | {args.out / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())