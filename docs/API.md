# API del backend (FastAPI)

> Para construir la UI empiecen por [`FRONT.md`](FRONT.md) (tipos, helper SSE, errores, comportamiento). Este archivo es la referencia de endpoints; la lógica interna está en [`BACKEND.md`](BACKEND.md) y el contrato completo en [`openapi.json`](openapi.json).

Backend que expone el RAG al front. Todo corre local.

- Código: `src/api/main.py` (usa `src/rag/agente.py`).
- Documentación interactiva (Swagger): `http://localhost:8000/docs`
- Esquema OpenAPI: `http://localhost:8000/openapi.json` (sirve para generar clientes TypeScript).

## Arranque

Requisitos: índice generado (`python -m src.rag.ingest`) y LM Studio con el modelo cargado y el servidor activo.

```bash
source .venv/bin/activate
python -m src.api.main        # desde la raíz del proyecto
# o: uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Al arrancar carga BGE-M3 y el índice una sola vez, por eso tarda unos segundos.

## Configuración (`src/config.py`)

| Variable | Valor por defecto | Qué hace |
|---|---|---|
| `API_HOST` | `127.0.0.1` | Usa `0.0.0.0` para exponerla en la red local |
| `API_PORT` | `8000` | Puerto |
| `CORS_ORIGENES` | `localhost:3000`, `localhost:5173`, `127.0.0.1:5173` | Orígenes del front permitidos. **Agrega el del tuyo si es otro** |
| `TOP_K` | `5` | Fragmentos que se pasan al LLM (se puede cambiar por petición) |
| `RAZONAMIENTO` | `"none"` | Apaga el razonamiento de Qwen3.5 en LM Studio |
| `MAX_TOKENS_RESPUESTA` | `150` | Longitud máxima de la respuesta |
| `SIM_SEGUNDOS_POR_LECTURA` | `2.0` | Velocidad de la transmisión simulada de salud |

## Endpoints

### `GET /salud`
Estado del servicio.

```json
{"estado": "ok", "fragmentos_indexados": 164, "llm_disponible": true, "modelo_llm": "qwen/qwen3.5-9b"}
```
`estado` es `"degradado"` y `llm_disponible` `false` si LM Studio no responde.

### `POST /preguntar`
Respuesta completa. Puede tardar minutos con el LLM en CPU; para la interfaz de chat usa mejor el stream.

Petición:
```json
{"pregunta": "¿Cuál es el límite de dosis de radiación en toda la carrera?", "top_k": 5}
```
- `pregunta`: 2 a 1000 caracteres (obligatoria).
- `top_k`: 1 a 10 (opcional).

Respuesta:
```json
{
  "respuesta": "Menos de 600 mSv ... [nasa 2.pdf, pág. 39]",
  "fuentes": [{"archivo": "nasa 2.pdf", "paginas": "39"}]
}
```
`paginas` es una página (`"39"`) o un rango (`"39-40"`).

Errores: `422` petición inválida, `503` LM Studio no responde.

### `POST /preguntar/stream`
Mismo cuerpo que `/preguntar`. Responde con **Server-Sent Events** (`text/event-stream`), en este orden:

| Evento | `data` (JSON) | Cuándo |
|---|---|---|
| `fuentes` | `[{"archivo": "...", "paginas": "..."}]` | Primero, apenas se recupera la documentación |
| `token` | `"texto"` | Varias veces, un trozo de la respuesta |
| `fin` | `""` | La respuesta terminó |
| `error` | `"mensaje"` | Falló la generación (p. ej. LM Studio apagado) |

Ejemplo de consumo en el front (`EventSource` no admite POST, así que se usa `fetch`):

```js
const res = await fetch("http://localhost:8000/preguntar/stream", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({pregunta}),
});
const reader = res.body.getReader();
const dec = new TextDecoder();
let buf = "";
for (;;) {
  const {done, value} = await reader.read();
  if (done) break;
  buf += dec.decode(value, {stream: true});
  const bloques = buf.split("\n\n");
  buf = bloques.pop();                       // el último puede estar incompleto
  for (const b of bloques) {
    const evento = b.match(/^event: (.+)$/m)?.[1];
    const m = b.match(/^data: (.+)$/m);
    if (!evento || !m) continue;               // ignora los ": ping"
    const datos = JSON.parse(m[1]);
    if (evento === "token") añadirTexto(datos);
    else if (evento === "fuentes") mostrarFuentes(datos);
    else if (evento === "error") mostrarError(datos);
  }
}
```

Prueba rápida con curl:
```bash
curl -N -X POST localhost:8000/preguntar/stream \
  -H 'Content-Type: application/json' \
  -d '{"pregunta": "¿Qué es el proyecto AMP?"}'
```

## Salud de los tripulantes (tiempo real)

Datos de `data/fisiologico.json`: 3 tripulantes (`astro_1` a `astro_3`) con `pulso` (bpm),
`spo2` (%), `presion_sistolica` y `presion_diastolica` (mmHg), una lectura cada 10 min durante
un día (144 lecturas por tripulante). Código: `src/api/salud.py` y `src/datos/salud.py`.

> **Simulado:** el archivo es un día ya grabado, así que el backend lo reproduce como una
> transmisión en vivo: cada `SIM_SEGUNDOS_POR_LECTURA` segundos (2 por defecto) "ocurre" una
> lectura nueva desde que arranca el servidor. Cada respuesta incluye `"simulado": true`.
> Cuando haya un sensor real solo se reemplaza `Monitor.indice_actual()`; el contrato de la API no cambia.

### `GET /tripulantes`
```json
[{"id": "astro_1", "variables": ["presion_diastolica", "presion_sistolica", "pulso", "spo2"], "lecturas_disponibles": 144}]
```

### `GET /tripulantes/{id}/salud?limite=60`
Foto actual: último valor de cada variable y las últimas `limite` lecturas (1 a 10000, por defecto 60).

```json
{
  "usuario": "astro_1",
  "timestamp_actual": "2026-11-01T00:30:00",
  "actual": {
    "pulso": {"valor": 57.6, "unidad": "bpm", "timestamp": "2026-11-01T00:30:00"},
    "spo2":  {"valor": 97.9, "unidad": "%",   "timestamp": "2026-11-01T00:30:00"}
  },
  "historial": [
    {"timestamp": "2026-11-01T00:20:00", "valores": {"pulso": 61.7, "spo2": 97.6, "presion_sistolica": 113.0, "presion_diastolica": 70.1}}
  ],
  "simulado": true
}
```
`404` si el tripulante no existe.

### `GET /tripulantes/{id}/salud/stream?limite=60`
Datos en vivo por SSE. Eventos:

| Evento | `data` | Cuándo |
|---|---|---|
| `snapshot` | Mismo JSON que `GET .../salud` | Al conectar |
| `lectura` | `{"timestamp": "...", "valores": {"pulso": 55.5, ...}}` | Cada lectura nueva |
| `fin` | `""` | Terminó la reproducción (no hay más datos) |

Cada cierto tiempo llega un comentario `: ping` de keep-alive; se puede ignorar.

```js
const res = await fetch(`http://localhost:8000/tripulantes/${id}/salud/stream`);
// leer res.body igual que en /preguntar/stream: "snapshot" pinta el estado inicial
// y cada "lectura" se agrega a las gráficas.
```
```bash
curl -N localhost:8000/tripulantes/astro_1/salud/stream
```

### `POST /tripulantes/reiniciar-simulacion`
Devuelve `204`. Reinicia la reproducción desde el inicio del día (útil para demos).

## Notas
- **Una consulta a la vez**: un candado serializa las peticiones, porque el modelo local corre en CPU. Las demás esperan su turno.
- **Latencia**: con Qwen3.5 9B en CPU, procesar los fragmentos antes del primer token toma más de un minuto (~15 tokens/s de prompt). Para acelerar: `top_k` menor (3), un modelo más chico (4B) o chunks más cortos (`MAX_TOKENS` en `config.py`).
- **Sin autenticación**: pensada para uso local. No la expongas con `0.0.0.0` en una red no confiable.

## Pendiente (próximas partes)
Endpoints para historial médico base, último evento y predicciones/anomalías, cuando existan esas piezas. La respuesta final combinará esos datos con la documentación.

## Inferencia, aptitud y notificaciones

Todo se calcula **por tripulante con su propio modelo personal** (`models/series/usuarios/<usuario>_<variable>.joblib`,
generado con `python -m src.series.analizar`). Los límites clínicos (`src/salud/referencias.py`) son solo una red de seguridad. Orientativo, no es diagnóstico médico.

- `GET /tripulantes/{id}/resumen?variables=pulso,spo2&limite=60`: por medida, estadísticas, tendencia, valor actual vs. rango esperado personal, nivel clínico; más magnitudes derivadas (presión de pulso, PAM, índice de choque) y patrones multi-variable. Sin `variables` = todas.
- `GET /tripulantes/{id}/aptitud`: `{apto, nivel, motivos, observaciones, recomendaciones, derivadas}`.
- `GET /tripulantes/{id}/notificaciones?desde=<id>`: alertas generadas al empeorar el estado de una medida (sin repetir).
- SSE `/tripulantes/{id}/salud/stream`: nuevo evento `notificacion` con `{id, usuario, timestamp, severidad, variable, mensaje}`.
- `POST /preguntar` y `/preguntar/stream`: nuevos campos opcionales `usuario` y `variables`; el agente resume esas medidas y la aptitud usando los datos calculados.

> **Códigos:** todas las respuestas anteriores incluyen códigos numéricos (`1001` saludable, `1010` riesgo, etc.) y los errores llevan `detail.codigo`. Catálogo completo en [`docs/CODIGOS.md`](CODIGOS.md) y en `GET /tripulantes/codigos`.
