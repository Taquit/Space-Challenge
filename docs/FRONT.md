# Guía para el equipo de Front

Todo lo que necesitan para construir la UI contra el backend. Referencia detallada de cada endpoint en [`API.md`](API.md); cómo funciona por dentro en [`BACKEND.md`](BACKEND.md); contrato máquina-legible en [`openapi.json`](openapi.json) (sirve para generar clientes con `openapi-typescript`, etc.).

## 1. Conexión

| | |
|---|---|
| URL base | `http://localhost:8000` |
| Swagger (probar endpoints) | `http://localhost:8000/docs` |
| Formato | JSON (`Content-Type: application/json`) y SSE para los streams |
| Autenticación | Ninguna (uso local) |
| CORS | Solo orígenes permitidos: `localhost:3000`, `localhost:5173`, `127.0.0.1:5173`. **Si su front corre en otro origen, avisen** y se agrega en `CORS_ORIGENES` (`src/config.py`). |

Arranque del backend (lo hace quien lo tenga instalado):
```bash
source .venv/bin/activate && python -m src.api.main
```
El backend tarda unos segundos en arrancar (carga el modelo de embeddings). Usen `GET /salud` para saber cuándo está listo.

## 2. Qué endpoint usar para cada pantalla

| Pantalla / componente | Endpoint |
|---|---|
| Selector de tripulante | `GET /tripulantes` |
| Tarjetas con signos vitales actuales | `snapshot` de `GET /tripulantes/{id}/salud/stream` (o `GET /tripulantes/{id}/salud`) |
| Gráficas en vivo | `snapshot.historial` + eventos `lectura` del mismo stream |
| Chat con la documentación | `POST /preguntar/stream` |
| Indicador de estado del sistema | `GET /salud` |

## 3. Tipos (TypeScript)

```ts
// ---- Tripulantes y salud ----
export interface Tripulante {
  id: string;                    // "astro_1"
  variables: string[];           // ["presion_diastolica","presion_sistolica","pulso","spo2"]
  lecturas_disponibles: number;  // 144
}

export interface Medicion {
  valor: number;
  unidad: string | null;         // "bpm" | "%" | "mmHg" | null si la variable no tiene unidad conocida
  timestamp: string;             // ISO 8601 SIN zona horaria: "2026-11-01T00:30:00"
}

export interface Lectura {
  timestamp: string;
  valores: Record<string, number>;   // { pulso: 71.2, spo2: 97.5, presion_sistolica: 114.1, presion_diastolica: 69.8 }
}

export interface EstadoSalud {
  usuario: string;
  timestamp_actual: string;
  actual: Record<string, Medicion>;  // último valor de cada variable
  historial: Lectura[];              // de la más antigua a la más reciente
  simulado: boolean;                 // true = reproducción de datos grabados, no un sensor real
}

// ---- Chat / RAG ----
export interface Fuente {
  archivo: string;   // "nasa 2.pdf"
  paginas: string;   // "39" o "39-40"
}
export interface Respuesta { respuesta: string; fuentes: Fuente[]; }

// ---- Estado del sistema ----
export interface Salud {
  estado: "ok" | "degradado";
  fragmentos_indexados: number;
  llm_disponible: boolean;
  modelo_llm: string | null;
}
```

### Variables que existen hoy
| `variable` | Unidad | Qué es |
|---|---|---|
| `pulso` | bpm | Frecuencia cardiaca |
| `spo2` | % | Saturación de oxígeno |
| `presion_sistolica` | mmHg | Presión arterial sistólica |
| `presion_diastolica` | mmHg | Presión arterial diastólica |

No hardcodeen la lista: léanla de `GET /tripulantes` (`variables`) y pinten una tarjeta/gráfica por cada una; así, si se agregan variables, la UI las toma sola. Las claves de `valores` y `actual` coinciden con esos nombres.

## 4. Cliente SSE reutilizable

`EventSource` del navegador **no soporta POST**, y el chat necesita POST. Usen `fetch` con este helper para ambos streams (sirve también para los GET):

```ts
export async function sse(
  url: string,
  onEvent: (evento: string, datos: any) => void,
  opts: { body?: unknown; signal?: AbortSignal } = {},
) {
  const res = await fetch(url, {
    method: opts.body ? "POST" : "GET",
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);

  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const bloques = buf.split("\n\n");
    buf = bloques.pop()!;                                // el último puede venir incompleto
    for (const b of bloques) {
      const ev = b.match(/^event: (.+)$/m)?.[1];
      const data = b.match(/^data: (.+)$/m)?.[1];
      if (!ev || data === undefined) continue;           // ignora los ": ping" de keep-alive
      onEvent(ev, JSON.parse(data));
    }
  }
}
```

Cancelar un stream (cambiar de tripulante, cerrar el chat): `AbortController.abort()` y pasar su `signal`. El backend detecta la desconexión y deja de enviar.

### Ejemplo: salud en vivo
```ts
const ctrl = new AbortController();
const base = "http://localhost:8000";

sse(`${base}/tripulantes/${id}/salud/stream?limite=60`, (ev, d) => {
  if (ev === "snapshot") {            // pinta estado inicial
    setActual((d as EstadoSalud).actual);
    setHistorial((d as EstadoSalud).historial);
  } else if (ev === "lectura") {      // llega cada ~2 s
    const l = d as Lectura;
    setActual(prev => actualizar(prev, l));       // actualiza tarjetas
    setHistorial(prev => [...prev, l].slice(-60)); // ventana deslizante
  } else if (ev === "fin") {
    // terminó la reproducción: mostrar "sin más datos" o reiniciar
  }
}, { signal: ctrl.signal });
```

### Ejemplo: chat con streaming
```ts
let texto = "";
await sse(`${base}/preguntar/stream`, (ev, d) => {
  if (ev === "fuentes") setFuentes(d as Fuente[]);   // llegan primero
  else if (ev === "token") { texto += d; setRespuesta(texto); }
  else if (ev === "error") setError(d as string);
  // "fin": quitar el indicador de "escribiendo"
}, { body: { pregunta } });
```

## 5. Comportamiento que la UI debe tener en cuenta

### Datos de salud
- **Son simulados**: la API reproduce un día grabado como si fuera en vivo (una lectura nueva cada ~2 s; el reloj simulado arranca cuando arranca el backend). Si `simulado` es `true`, conviene un aviso discreto tipo "Datos de demostración".
- **El stream termina**: tras la última lectura del día llega `fin`. Los datos van del `2026-11-01T00:00:00` al `23:50:00`. Para repetir la demo: `POST /tripulantes/reiniciar-simulacion` (responde `204`) y reconectar el stream.
- **Timestamps**: ISO 8601 **sin zona horaria**; trátenlos como hora local de la misión, no los conviertan con `new Date()` asumiendo UTC sin cuidado.
- **Reconexión**: al reconectar, el `snapshot` vuelve a traer el estado completo; reemplacen (no acumulen) el historial.
- **El backend no clasifica los valores** (no dice si un pulso es "alto" o "peligroso"). Rangos de normalidad y alertas todavía no existen en la API.
- Los números llegan con 1 decimal; muestren tal cual.

### Chat (documentación técnica)
- **Es lento**: el modelo corre en CPU. El **primer token puede tardar de decenas de segundos a más de un minuto**, y luego salen ~2 tokens/s. Usen siempre `/preguntar/stream`, muestren un indicador de "buscando en la documentación…" desde que se envía la pregunta, y pinten las fuentes en cuanto llegan (llegan antes del texto).
- **Una consulta a la vez**: el backend atiende las preguntas en cola. Deshabiliten el botón de enviar mientras haya una respuesta en curso.
- **Respuestas cortas** por diseño (1-2 oraciones, máx. 150 tokens) y con la cita en el texto: `... [nasa 2.pdf, pág. 39]`. Si la respuesta no está en la documentación, el modelo responde `No está en la documentación.`
- **Fuentes**: muéstrenlas siempre como lista separada (`archivo` + `paginas`); es lo que permite al usuario verificar.
- La pregunta debe tener entre **2 y 1000 caracteres**; valídenlo antes de enviar.
- No es un diagnóstico médico: respondan lo que dice la documentación. Recomendamos un texto fijo en la UI tipo "Información de referencia, no sustituye valoración médica".

## 6. Errores

| Situación | Cómo llega |
|---|---|
| Tripulante inexistente | `404` `{"detail": "Tripulante 'x' no encontrado"}` |
| Pregunta inválida (muy corta/larga, `top_k` fuera de rango) | `422` `{"detail": [{"loc": ["body","pregunta"], "msg": "...", "type": "..."}]}` |
| LM Studio apagado en `POST /preguntar` | `503` `{"detail": "LM Studio no responde. ..."}` |
| LM Studio apagado en `POST /preguntar/stream` | Responde `200` y envía evento `error` con el mensaje (las `fuentes` pueden haber llegado antes) |
| Backend apagado / arrancando | Falla de red (`fetch` rechaza). Reintentar `GET /salud` cada pocos segundos |

Usen `GET /salud` para un indicador de estado: `estado: "degradado"` o `llm_disponible: false` significa que el chat no va a responder, pero **los datos de salud siguen funcionando** (no dependen del LLM).

## 7. Lo que todavía no existe

Para que no lo esperen en la UI aún:
- Historial médico base del tripulante y último evento clínico.
- Predicciones y detección de anomalías (parte de series de tiempo).
- Alertas / rangos de referencia por variable.
- Autenticación y varios usuarios simultáneos en el chat (hay una sola cola).

Cuando se agreguen, se documentarán aquí y en `API.md`.

## 8. Prueba rápida sin front

```bash
curl localhost:8000/tripulantes
curl "localhost:8000/tripulantes/astro_1/salud?limite=5"
curl -N localhost:8000/tripulantes/astro_1/salud/stream
curl -N -X POST localhost:8000/preguntar/stream -H 'Content-Type: application/json' \
     -d '{"pregunta": "¿Cuál es el límite de dosis de radiación en toda la carrera?"}'
```

## 9. Voz: leer en voz alta lo que devuelve el backend

El front lee en voz alta las respuestas del chat y las notificaciones. Se hace **en el navegador** con la Web Speech API (`speechSynthesis`): sin dependencias, sin endpoint nuevo y sin internet. Copien [`front/voz.ts`](front/voz.ts) a su proyecto.

| Qué se lee | De dónde sale | Cómo |
|---|---|---|
| Respuesta del chat | eventos `token` de `POST /preguntar/stream` | `lectorStream()`: habla cada oración en cuanto se completa (no espera al final, el modelo es lento) |
| Respuesta completa | `respuesta` de `POST /preguntar` | `voz.hablar(r.respuesta)` |
| Alertas | evento `notificacion` del stream de salud | `voz.hablar(textoNotificacion(n))` |
| Aptitud | `GET /tripulantes/{id}/aptitud` | `voz.hablar(textoAptitud(a))` |

```ts
import { voz, lectorStream, textoNotificacion } from "./voz";

// Chat
const lector = lectorStream();
let texto = "";
await sse(`${base}/preguntar/stream`, (ev, d) => {
  if (ev === "fuentes") setFuentes(d);
  else if (ev === "token") { texto += d; setRespuesta(texto); lector.agregar(d); }
  else if (ev === "fin") lector.fin();
  else if (ev === "error") { lector.cancelar(); setError(d); }
}, { body: { pregunta } });

// Notificaciones (dentro del handler del stream de salud)
if (ev === "notificacion") voz.hablar(textoNotificacion(d), { interrumpir: d.severidad === "CRITICO" });

// Botón de silencio (la preferencia se guarda en localStorage)
<button onClick={() => voz.activar(!voz.activa)}>{voz.activa ? "🔊" : "🔇"}</button>
```

A tener en cuenta:
- **El texto se limpia antes de leerse** (`limpiar`): se quitan las citas `[nasa 2.pdf, pág. 39]` y el markdown, y `spo2`, `presion_sistolica`, `bpm`, etc. se dicen con su nombre completo. En pantalla sigan mostrando el texto original.
- **El navegador bloquea el audio hasta que el usuario interactúa con la página.** El chat no tiene problema (hay un clic al enviar); las notificaciones no sonarán si llegan antes del primer clic o tecla.
- **Voz en español y sin internet**: el módulo elige una voz `es-*` local. Windows y macOS ya traen una. En Linux, Chrome/Firefox usan `speech-dispatcher` + `espeak-ng` (`sudo dnf install speech-dispatcher espeak-ng`). Las voces "Google español" de Chrome **requieren internet**; por eso se prefieren las locales. `voz.hayVozEnEspanol()` dice si hay una instalada y `voz.disponible` si el navegador soporta voz.
- Al cambiar de tripulante o cancelar una pregunta, llamen `voz.callar()` (o `lector.cancelar()`).
- Las preguntas del usuario no se leen, solo lo que responde el backend.
