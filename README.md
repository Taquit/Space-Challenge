# Space Challenge

Monitoreo de salud física y mental de astronautas en misiones de larga duración.
Todo corre **local y sin internet** en el entorno final, con prioridad en ahorrar
espacio y tiempo de cómputo.

El proyecto tiene dos partes:

| Parte | Qué hace | Carpeta |
|---|---|---|
| 1. RAG + agente | Responde preguntas técnicas usando la documentación en PDF | `src/rag/` |
| 2. Series de tiempo | Predice y detecta anomalías en las mediciones fisiológicas (JSON) | `src/series/` |

---

## Estructura

```
space-repo/
├── README.md
├── requirements.txt
├── .gitignore
├── docs/
│   ├── CONTEXT.md
│   ├── STACK-1.md
│   ├── STACK-2.md
│   ├── API.md
│   ├── FRONT.md
│   ├── BACKEND.md
│   └── openapi.json
├── data/
│   ├── fisiologico.json
│   ├── pdfs/
│   └── indices/
├── models/
│   ├── chronos-2/
│   └── bge-m3/
├── scripts/
│   └── descargar_modelos.py
├── src/
│   ├── config.py
│   ├── api/
│   │   ├── main.py
│   │   ├── salud.py
│   │   └── sse.py
│   ├── datos/
│   │   └── salud.py
│   ├── rag/
│   │   ├── prepare_chunks.py
│   │   ├── ingest.py
│   │   └── agente.py
│   └── series/                (pendiente)
│       ├── prueba.py
│       ├── cargar.py
│       └── finetune.py
└── .venv/
```

---

## Qué hace cada archivo y cómo lo hace

### Raíz

- **`README.md`**: este documento.
- **`requirements.txt`**: dependencias de ambas partes (`torch`, `pypdf`,
  `pypdf`, `sentence-transformers`, `faiss-cpu`, `openai`, `fastapi`, `uvicorn`, `huggingface_hub`,
  `chronos-forecasting`, `pandas`, `numpy`, `scikit-learn`, `statsmodels`).
- **`.gitignore`**: evita subir al repositorio lo pesado o regenerable
  (`.venv/`, `models/`, `data/indices/`, `__pycache__/`).

### `docs/`

- **`CONTEXT.md`**: descripción del reto, objetivos del proyecto e historias de usuario.
- **`FRONT.md`**: guía para el equipo de front (tipos TypeScript, helper SSE, errores, comportamiento de la UI).
- **`API.md`**: referencia de endpoints del backend FastAPI y eventos SSE.
- **`BACKEND.md`**: arquitectura y lógica interna del backend (RAG, simulación de salud, configuración).
- **`openapi.json`**: contrato OpenAPI exportado (regenerable; ver abajo).
- **`STACK-1.md`**: documentación técnica del RAG (componentes, flujo, parámetros, limitaciones).
- **`STACK-2.md`**: documentación técnica del stack de la parte 2
  (Chronos-2, flujo de baseline, fine-tuning y alertas).

### `data/`

- **`fisiologico.json`**: muestra de métricas fisiológicas (pulso, SpO2, etc.).
  Es la entrada de la parte 2.
- **`pdfs/`**: aquí se colocan los PDFs de documentación técnica para la parte 1.
- **`indices/`**: salida generada por `ingest.py` (`indice.faiss`, `chunks.json` y `report.md`).
  Se puede borrar y volver a generar.

### `models/` (pesos, no se suben a git)

- **`chronos-2/`**: pesos de `amazon/chronos-2` (modelo de series de tiempo, 120M de parámetros).
- **`bge-m3/`**: pesos de `BAAI/bge-m3` (modelo de embeddings para el RAG).

### `scripts/`

- **`descargar_modelos.py`**: descarga los pesos de Chronos-2 y BGE-M3 desde
  Hugging Face a `models/` usando `snapshot_download`. **Es el único paso que
  necesita internet**; se corre una vez y después todo funciona offline.

### `src/config.py`

Configuración central. Define las rutas (`PDFS_DIR`, `INDICE`, `CHUNKS`,
`MODELO_EMB`, `REPORTE`) calculadas a partir de la raíz del proyecto, y los
parámetros del RAG: `MAX_TOKENS`, `MIN_TOKENS`, `OVERLAP_ORACIONES` (chunking), `TOP_K`
(cuántos fragmentos se pasan al LLM), la URL de LM Studio, el nombre del modelo
LLM y la temperatura. Ningún otro script escribe rutas a mano.

### `src/rag/` (parte 1)

- **`prepare_chunks.py`**: limpieza y chunking de PDFs (con `pypdf`). Quita
  índices, encabezados y pies repetidos, ligaduras y errores de OCR; en
  estándares NASA genera un chunk por requisito `[V1 xxxx]` y en el resto
  divide por secciones con ventanas de oraciones. Cada chunk lleva un
  encabezado `[documento | sección | requisito]`. Las reglas por PDF están en
  `PROFILES`. Lo usa `ingest.py`, y también puede correrse solo
  (`python -m src.rag.prepare_chunks --pdf-dir data/pdfs --out salida/`).

- **`ingest.py`**: construye el índice de búsqueda.
  1. Procesa cada PDF de `data/pdfs/` con `prepare_chunks.process_pdf`
     (chunks con archivo y rango de páginas).
  2. Convierte cada fragmento en un vector con BGE-M3 (`sentence-transformers`).
  3. Guarda los vectores en un índice FAISS (`indice.faiss`), los textos con sus
     metadatos en `chunks.json` y un `report.md` para revisar la calidad del
     chunking (páginas omitidas, chunks sospechosos, muestras).
  Avisa si un PDF no produce texto (probablemente está escaneado y requeriría OCR).
  Se vuelve a correr cuando cambien los PDFs.

- **`agente.py`**: responde preguntas por consola.
  1. Carga el índice, los fragmentos y el modelo de embeddings.
  2. Convierte la pregunta en un vector y busca en FAISS los `TOP_K` fragmentos
     más parecidos (la búsqueda es **siempre obligatoria**, no depende de que el
     modelo decida buscar).
  3. Envía al LLM (servido por LM Studio, API compatible con OpenAI) un prompt
     con esos fragmentos y la pregunta, con instrucciones de responder solo con
     base en ellos y citar `[archivo, pág. N]` (o rango `N-M`).
  4. Muestra la respuesta y la lista de fuentes consultadas.

### `src/api/` (backend)

- **`main.py`**: API FastAPI que expone el RAG al front. Endpoints `GET /salud`,
  `POST /preguntar` y `POST /preguntar/stream` (SSE, la respuesta llega token
  por token). Carga el agente una vez al arrancar, habilita CORS para el front
  (`CORS_ORIGENES` en `config.py`) y atiende una consulta a la vez. Detalle en
  [`docs/API.md`](docs/API.md).

- **`salud.py`**: endpoints `GET /tripulantes`, `GET /tripulantes/{id}/salud` y
  `GET /tripulantes/{id}/salud/stream` (SSE) con los datos de salud para la UI.
  Los datos vienen de `src/datos/salud.py`, que agrupa `fisiologico.json` por
  tripulante y lo reproduce como transmisión en vivo (simulada, una lectura cada
  `SIM_SEGUNDOS_POR_LECTURA` s).
- **`sse.py`**: formateo de eventos Server-Sent Events compartido por los endpoints.

### `src/series/` (parte 2)

- **`prueba.py`**: prueba de que Chronos-2 funciona. Carga los pesos locales,
  genera 14 días de pulso sintético (una medición por hora con ciclo diario más
  ruido), arma el DataFrame (`id`, `timestamp`, `target`) y llama a
  `predict_df` para predecir las siguientes 24 horas con los cuantiles 5%, 50%
  y 95%.
- **`cargar.py`** *(pendiente)*: convertirá `fisiologico.json` al formato
  `id / timestamp / target`, una variable a la vez, ordenado por tiempo.
- **`finetune.py`** *(pendiente)*: fine-tuning de Chronos-2 por usuario, solo si
  mejora el error frente al modelo sin entrenar y frente al baseline.

---

## Cómo funciona cada parte

### Parte 1: RAG

```
PDFs ──ingest.py──> fragmentos ──BGE-M3──> vectores ──> indice.faiss + chunks.json
                                                              │
pregunta ──BGE-M3──> vector ──búsqueda──> top-k fragmentos ───┘
                                              │
                          fragmentos + pregunta ──> LLM (LM Studio) ──> respuesta con citas
```

### Parte 2: series de tiempo

1. Se convierte el JSON a una serie por variable y por usuario.
2. Se mide un baseline simple (promedio móvil exponencial) para tener contra qué comparar.
3. Chronos-2 predice sin entrenar (zero-shot) y se compara el error con el baseline.
4. Si el error no es suficientemente bueno, se hace fine-tuning por usuario.
5. Alerta: si varios valores reales seguidos caen fuera del rango predicho
   (cuantiles 5% a 95%), se marca una anomalía.

---

## Instalación y uso

Todos los comandos se corren desde la raíz del proyecto.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# Una sola vez, con internet:
python scripts/descargar_modelos.py
```

**Parte 1**

```bash
# 1. Copia los PDFs a data/pdfs/
python -m src.rag.ingest
# 2. En LM Studio: carga Qwen3.5 4B (Instruct, Q4_K_M) y activa Developer > Start Server
python -m src.rag.agente
```

**Backend para el front**

```bash
python -m src.api.main      # http://localhost:8000/docs
```

Si cambian los endpoints, regenera el contrato para el front:

```bash
python -c "import json; from src.api.main import app; json.dump(app.openapi(), open('docs/openapi.json','w'), ensure_ascii=False, indent=2)"
```

**Parte 2**

```bash
python -m src.series.analizar   # entrena/reentrena solo el modelo de cada usuario cuando hace falta y genera data/resultados/deviations.json; el agente lo usa como contexto
```

---

# Space-Challenge
