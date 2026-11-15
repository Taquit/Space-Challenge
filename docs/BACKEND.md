# Backend: arquitectura y lógica

Cómo está armado el backend por dentro. Para consumir la API desde la UI, ver [`FRONT.md`](FRONT.md) y [`API.md`](API.md).

## Visión general

```
                        ┌──────────────────────────────────────────┐
   Front ── HTTP/SSE ──>│ FastAPI  (src/api/main.py)               │
                        │   ├─ /salud, /preguntar, /preguntar/stream│──> src/rag/agente.py ──> FAISS + BGE-M3
                        │   └─ /tripulantes/...  (src/api/salud.py)│        │                      (índice local)
                        └──────────────────────────────────────────┘        └──> LM Studio (LLM local, :1234)
                                         │
                                         └──> src/datos/salud.py ──> data/fisiologico.json
```

Todo corre local y offline. Procesos: el backend (puerto 8000) y el servidor de LM Studio (puerto 1234).

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `src/config.py` | Rutas y parámetros: RAG, LLM, API, simulación |
| `src/api/main.py` | App FastAPI, CORS, `/salud`, `/preguntar`, `/preguntar/stream` |
| `src/api/salud.py` | Router `/tripulantes/...`: listado, foto actual, stream en vivo |
| `src/api/sse.py` | Formato de eventos Server-Sent Events |
| `src/datos/salud.py` | Carga y agrupa `fisiologico.json`; reloj de la simulación en vivo |
| `src/datos/cognitivo.py` | Esquema y lectura/escritura de `data/cognitivo.json` (sesiones PVT, DSST, Matrix) |
| `src/salud/cognitivo.py` | Inferencia cognitiva: línea base, z de deterioro, persistencia, deriva, patrones (ver `COGNITIVO.md`) |
| `src/rag/prepare_chunks.py` | Limpieza y chunking de PDFs |
| `src/rag/ingest.py` | Construye el índice FAISS a partir de los PDFs |
| `src/rag/agente.py` | Búsqueda + prompt + generación con el LLM |

## Parte A: Consulta de documentación (RAG)

### Construcción del índice (offline, una vez por cambio de PDFs)
`python -m src.rag.ingest`
1. `prepare_chunks` lee cada PDF de `data/pdfs/` con `pypdf`, quita índices, encabezados/pies repetidos, ligaduras y errores de OCR (reglas por documento en `PROFILES`).
2. Parte en chunks: uno por requisito `[V1 xxxx]` en estándares NASA; en el resto, por secciones con ventanas de oraciones. Máximo `MAX_TOKENS`=400. Cada chunk lleva el encabezado `[documento | §sección | requisito]`.
3. BGE-M3 convierte cada chunk en un vector; se guardan en `data/indices/indice.faiss`, con los textos y páginas en `chunks.json` y un `report.md` de calidad.

### Atención de una pregunta
```
pregunta ─> BGE-M3 ─> vector ─> FAISS top_k ─> fragmentos
fragmentos + pregunta ─> prompt (SYSTEM + contexto) ─> LLM ─> tokens
```
- **Búsqueda siempre obligatoria**: el LLM no decide si buscar. Siempre recibe los `top_k` (5) fragmentos más parecidos.
- **Prompt (`SYSTEM`)**: responder solo con los fragmentos, ser muy conciso (1-2 oraciones), citar `[archivo, pág. N]`, y si no está: `No está en la documentación.`
- **LLM**: modelo cargado en LM Studio vía API compatible con OpenAI. Si `MODELO_LLM` es `None` usa el primero cargado. El razonamiento se apaga con `reasoning_effort: "none"` (`RAZONAMIENTO`); sin esto Qwen3.5 gasta minutos "pensando".
- **Límite de salida**: `MAX_TOKENS_RESPUESTA`=150.
- **Fuentes**: se devuelven deduplicadas como `{archivo, paginas}`; `paginas` es una página o un rango si el chunk cruza páginas.

### Funciones de `agente.py`
| Función | Qué hace |
|---|---|
| `buscar(consulta, k)` | Top-k fragmentos desde FAISS |
| `preparar(pregunta, k)` | `(mensajes, fragmentos)` listos para el LLM |
| `generar(mensajes)` | Generador de tokens del LLM (streaming) |
| `fuentes_de(frags)` | Lista de fuentes serializable |
| `preguntar(pregunta, k)` | `(texto, fuentes)` completo |

La CLI (`python -m src.rag.agente`) y la API usan las mismas funciones.

### Concurrencia
El modelo corre en CPU, así que un `threading.Lock` serializa las consultas al RAG: una a la vez, las demás esperan. El tiempo de espera hasta el primer token es dominado por el procesamiento del prompt (~15 tokens/s con el 9B), y luego ~2 tokens/s de generación.

## Parte B: Salud en tiempo real

### Datos
`data/fisiologico.json`: lista de `{usuario, timestamp, variable, valor}` (formato largo). Hoy: 3 tripulantes × 4 variables × 144 instantes (cada 10 min, un día).

`Monitor` (`src/datos/salud.py`) los agrupa al arrancar:
```
{ "astro_1": [ ("2026-11-01T00:00:00", {"pulso": 71.2, "spo2": 97.5, ...}), ... ] }
```
ordenado por tiempo. Las unidades salen del diccionario `UNIDADES` (pulso bpm, spo2 %, presiones mmHg); una variable nueva sin unidad conocida llega con `unidad: null`.

### Datos de sueño
`data/sueno.json` (lista de noches `{usuario, timestamp, fase, medicacion, valores}`) sale de `data/sleep/` con `python scripts/importar_sueno.py`: mapea
los sujetos del estudio a tripulantes (`C1G0003→astro_1`, `C1G0002→astro_2`), promedia los registros duplicados de una misma noche y convierte h:mm a minutos/horas.
`Monitor` los carga aparte (`self.sueno`) y los reproduce con su propio índice (`indice_sueno`): una noche cada `SIM_SEGUNDOS_POR_LECTURA` s.
`series_por_variable` las une a los signos vitales, así que resumen, aptitud, notificaciones y chat las ven como una variable más (sin modelo personal).
Ruta configurable con `DATOS_SUENO`. Un tripulante sin sueño (astro_3) funciona igual, sin esas variables.

### Datos cognitivos
`data/cognitivo.json` (`[{usuario, sesiones: [...]}]`, ruta configurable con `DATOS_COGNITIVO`) guarda las métricas crudas de cada sesión; `scripts/simular_cognitivo.py`
genera sesiones de demo (astro_1 estable, astro_2 caída súbita, astro_3 deriva lenta). `DatosCognitivo` valida el esquema (pydantic) y guarda con `POST /tripulantes/{id}/cognitivo`.
A diferencia de los vitales y el sueño, **no se reproducen en el tiempo simulado**: se leen completas. Las inferencias se recalculan en cada lectura. Los resultados entran a
`/aptitud`, `/resumen`, las notificaciones (`sincronizar_cognitivo`) y el contexto del chat (`estado_fisiologico(..., sesiones_cog)`). Solo observa: nunca produce no apto.

### Simulación de "tiempo real"
El archivo es un día ya grabado, así que se reproduce como transmisión en vivo:
- Al arrancar (o al `POST /tripulantes/reiniciar-simulacion`) se guarda `t0`.
- `indice_actual() = min( (ahora - t0) / SIM_SEGUNDOS_POR_LECTURA , última_lectura )`. Con el valor por defecto (2 s), cada 2 s "ocurre" una lectura nueva.
- Todos los tripulantes comparten el mismo reloj; al llegar a la última lectura (23:50) la reproducción se detiene.

Para un sensor real solo hay que sustituir `indice_actual()` y la carga de datos; la API y el contrato no cambian.

### Stream (`GET /tripulantes/{id}/salud/stream`)
1. Envía `snapshot` (estado completo, con `sueno`).
2. Cada 0.5 s compara el índice actual con el último enviado; si avanzó, envía un evento `lectura` por **cada** lectura nueva (no se pierde ninguna si el cliente va lento).
   También envía un evento `sueno` por cada noche nueva (mismo reloj, índice propio).
3. Cada ~10 s sin novedades envía `: ping` (keep-alive).
4. Al llegar al final de lecturas **y** noches envía `fin` y cierra. Si el cliente se desconecta, termina.

El stream no usa el candado del RAG: la salud funciona aunque el chat esté ocupado o el LLM apagado.

## Configuración (`src/config.py`)

| Variable | Defecto | Efecto |
|---|---|---|
| `TOP_K` | 5 | Fragmentos que recibe el LLM |
| `MAX_TOKENS` / `MIN_TOKENS` / `OVERLAP_ORACIONES` | 400 / 60 / 1 | Chunking (requiere re-`ingest`) |
| `LMSTUDIO_URL` | `http://localhost:1234/v1` | Servidor del LLM |
| `MODELO_LLM` | `None` | `None` = primer modelo cargado |
| `TEMPERATURA` | 0.2 | |
| `RAZONAMIENTO` | `"none"` | Apaga razonamiento (Qwen3.5) |
| `MAX_TOKENS_RESPUESTA` | 150 | Longitud máxima de la respuesta |
| `API_HOST` / `API_PORT` | `127.0.0.1` / 8000 | Dirección del backend |
| `CORS_ORIGENES` | localhost 3000/5173 | Orígenes del front permitidos |
| `SIM_SEGUNDOS_POR_LECTURA` | 2.0 | Velocidad de la simulación |

## Puesta en marcha

```bash
# 1. LLM (una vez descargado): cargar y servir
lms load qwen/qwen3.5-9b && lms server start
# 2. Índice (solo si cambiaron los PDFs)
python -m src.rag.ingest
# 3. Backend
python -m src.api.main
```
Comprobar: `curl localhost:8000/salud` → `estado: "ok"`.

## Decisiones de diseño
- **Recuperación obligatoria y contexto armado en código**, no un agente con tool calling: con modelos locales de 4-9B el tool calling es poco fiable, y una sola llamada al LLM es más rápida en CPU.
- **SSE en vez de WebSocket**: unidireccional, más simple, y funciona con `fetch`. Se usa POST para el chat, por eso el front no puede usar `EventSource`.
- **El agente carga al arrancar** (`lifespan`): BGE-M3 y el índice se cargan una vez, no por petición.
- **Sin autenticación**: uso local. No exponer con `API_HOST="0.0.0.0"` en redes no confiables.

## Limitaciones y trabajo pendiente
- Latencia alta del LLM en CPU; mejora con un modelo 4B, menos `TOP_K` o chunks más cortos.
- Datos de salud simulados; falta integrar la fuente real.
- Sin endpoints todavía para historial médico base, último evento, predicciones/anomalías ni alertas (la respuesta final del agente combinará esos datos con la documentación).
- Sin pruebas automáticas ni evaluación del RAG.
