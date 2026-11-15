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
├── umbrales.env               (umbrales configurables, sin tocar código)
├── tests/                     (test_salud.py, test_cognitivo.py)
├── docs/
│   ├── CONTEXT.md
│   ├── INFERENCIAS.md
│   ├── UMBRALES.md
│   ├── CODIGOS.md
│   ├── COGNITIVO.md
│   ├── PRUEBAS_COGNITIVAS.md
│   ├── STACK-1.md
│   ├── STACK-2.md
│   ├── API.md
│   ├── FRONT.md
│   ├── BACKEND.md
│   └── openapi.json
├── data/
│   ├── fisiologico.json
│   ├── sueno.json             (generado desde data/sleep/)
│   ├── cognitivo.json         (sesiones PVT/DSST/Matrix; scripts/simular_cognitivo.py)
│   ├── sleep/                 (dataset crudo de actigrafía BRSM)
│   ├── pdfs/
│   └── indices/
├── models/
│   ├── chronos-2/
│   ├── bge-m3/
│   └── voz/                   (voces de Piper; scripts/descargar_voces.py)
├── scripts/
│   ├── descargar_modelos.py
│   ├── descargar_voces.py
│   ├── simular_cognitivo.py
│   └── importar_sueno.py
├── src/
│   ├── config.py
│   ├── api/
│   │   ├── main.py
│   │   ├── salud.py
│   │   └── sse.py
│   ├── datos/
│   │   ├── salud.py
│   │   └── cognitivo.py
│   ├── salud/                 (inferencias, aptitud, notificaciones, cognitivo)
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
- **`INFERENCIAS.md`**: cada inferencia de salud (límites, modelo personal, deriva, aptitud, notificaciones, sueño).
- **`UMBRALES.md`**: cómo ajustar los umbrales (`umbrales.env`, sin tocar código).
- **`CODIGOS.md`**: catálogo de códigos de respuesta (1xxx-9xxx).
- **`COGNITIVO.md`** y **`PRUEBAS_COGNITIVAS.md`**: plan del módulo cognitivo (PVT, DSST, Matrix) y qué mide cada prueba.
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
- **`voz/`**: voces de Piper para Orbi: `es_MX-claude-high` (español de México,
  Apache-2.0) y `en_US-ljspeech-high` (inglés de EE. UU., dataset de dominio público).

### `scripts/`

- **`descargar_modelos.py`**: descarga los pesos de Chronos-2 y BGE-M3 desde
  Hugging Face a `models/` usando `snapshot_download`. **Es el único paso que
  necesita internet**; se corre una vez y después todo funciona offline.
- **`descargar_voces.py`**: descarga las voces de Piper (`VOCES` en
  `src/config.py`) de `rhasspy/piper-voices` a `models/voz/`. Con `--probar`
  genera `models/voz/prueba_<idioma>.wav` para escucharlas.
- **`importar_sueno.py`**: convierte el dataset de actigrafía de `data/sleep/` a
  `data/sueno.json` (una fila por noche: latencia, duración, eficiencia y
  medicación; promedia duplicados y asigna sujetos a `astro_1`/`astro_2`).

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
- **`POST /voz`** (en `main.py`, síntesis en `src/voz.py`): texto a voz con Piper,
  `{"texto": "...", "idioma": "es" | "en"}` → WAV. Si la voz no está instalada
  responde 503 con código 9005 y el front usa la voz del navegador.
  `/preguntar` y `/preguntar/stream` aceptan `"idioma": "en"` para que Orbi
  responda en inglés.

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

## Requisitos

| Necesitas | Para qué | Notas |
|---|---|---|
| Python 3.10 o superior | Todo el backend | Se probó con 3.14 |
| Dependencias de `requirements.txt` (`torch` aparte, versión CPU) | RAG, series de tiempo y API | Instalación abajo |
| Pesos de `BAAI/bge-m3` en `models/bge-m3/` | Embeddings del RAG | `scripts/descargar_modelos.py` (único paso con internet) |
| Pesos de `amazon/chronos-2` en `models/chronos-2/` | Solo si vas a (re)entrenar modelos de la parte 2 | Los modelos ya entrenados por tripulante vienen en `models/series/` |
| [LM Studio](https://lmstudio.ai) con un modelo cargado (p. ej. Qwen3.5 4B o 9B) y el servidor local activo en `http://localhost:1234/v1` | Solo el chat (`/preguntar`) | Sin LM Studio todo lo demás funciona; el chat responde 503 con código 9003 |
| Voces de Piper en `models/voz/` | La voz de Orbi (español e inglés) | `scripts/descargar_voces.py`; sin ellas el front usa la voz del navegador |
| PDFs en `data/pdfs/` y el índice generado con `python -m src.rag.ingest` | Búsqueda del RAG | El índice (`data/indices/`) no se sube a git: hay que generarlo |
| Node.js y el proyecto del front | Solo si quieres la interfaz | El front **no está en este repo**; ver `docs/FRONT.md` |

No hace falta GPU: todo está pensado para correr en CPU, sin internet una vez descargados los modelos. El LLM es lo más lento (más de un minuto hasta el primer token con un modelo de 9B en CPU).

---

## Despliegue de la demo

La demo corre toda en una sola máquina, sin internet: el LLM en LM Studio, el backend FastAPI y, opcionalmente, el front.

**Preparación (una sola vez, con internet)**

```bash
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python scripts/descargar_modelos.py          # pesos de BGE-M3 y Chronos-2
python scripts/descargar_voces.py --probar   # voces de Orbi (Piper, español e inglés)
# copia los PDFs a data/pdfs/ y construye el índice:
python -m src.rag.ingest
# datos de demo (ya vienen en el repo; regenerar solo si cambian):
python scripts/importar_sueno.py             # data/sueno.json
python scripts/simular_cognitivo.py          # data/cognitivo.json
python -m src.series.analizar                # data/resultados/deviations.json (modelo personal)
```

**Arranque (cada vez que se presenta)**

```bash
# 1. LLM: en LM Studio carga el modelo y activa Developer > Start Server
#    (o por consola: lms load qwen/qwen3.5-9b && lms server start)
# 2. Backend (tarda unos segundos: carga BGE-M3 y el índice)
source .venv/bin/activate
python -m src.api.main                       # http://localhost:8000
# 3. Comprobar que está listo
curl localhost:8000/salud                    # estado: "ok" y llm_disponible: true
# 4. Front (en su propio proyecto)
npm run dev                                  # http://localhost:5173 (u otro origen permitido)
```

**Qué se ve en la demo**

- **Tripulantes** `astro_1`, `astro_2` y `astro_3`: signos vitales y sueño se reproducen como si fueran en vivo (una lectura cada 2 s, ajustable con `SIM_SEGUNDOS_POR_LECTURA`). Son datos grabados, no un sensor real.
- **Aptitud y notificaciones** (`/tripulantes/{id}/aptitud`, `/notificaciones` y el stream SSE): salen de los límites clínicos y del modelo personal de cada persona.
- **Cognitivo:** `astro_1` estable, `astro_2` con caída súbita y `astro_3` con deriva lenta (`/tripulantes/{id}/cognitivo/resumen`). Las sesiones están completas desde el inicio; no se reproducen en el tiempo.
- **Chat** (`/preguntar/stream` con `usuario`): responde con citas a los PDFs y con las cifras ya calculadas del tripulante.

**Antes de repetir la demo:** `curl -X POST localhost:8000/tripulantes/reiniciar-simulacion` reinicia la reproducción y las notificaciones. Las sesiones cognitivas enviadas con `POST` se guardan en `data/cognitivo.json`; para volver a los datos de demo corre `python scripts/simular_cognitivo.py`.

**Ajustes comunes**

- Otro origen del front: agrégalo en `CORS_ORIGENES` (`src/config.py`).
- Mostrar el backend a otra máquina de la red local: `API_HOST = "0.0.0.0"` en `src/config.py`. No tiene autenticación, así que solo en una red de confianza.
- Cambiar un criterio clínico o cognitivo: edita `umbrales.env` y reinicia el backend (ver `docs/UMBRALES.md`).
- Si el chat va lento: usa un modelo más chico, `TOP_K` menor o chunks más cortos.
- Documentación interactiva de la API: `http://localhost:8000/docs`.

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
python scripts/descargar_voces.py
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

**Datos de sueño y cognitivos** (si cambia el dataset de `data/sleep/` o quieres regenerar la simulación)

```bash
python scripts/importar_sueno.py    # regenera data/sueno.json
python scripts/simular_cognitivo.py # regenera data/cognitivo.json (datos simulados)
```

**Pruebas**

```bash
python -m pytest tests -q
```

**Parte 2**

```bash
python -m src.series.analizar   # entrena/reentrena solo el modelo de cada usuario cuando hace falta y genera data/resultados/deviations.json; el agente lo usa como contexto
```

