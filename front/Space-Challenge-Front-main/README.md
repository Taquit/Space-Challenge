# ORBITAL · Front

Interfaz de ORBITAL (NASA Space Apps CDMX 2026, equipo Tacos de Asada): monitoreo de salud física y mental de astronautas. **Software local, sin internet.** Diseño generado en Claude Design y conectado al backend real ([`Taquit/Space-Challenge`](https://github.com/Taquit/Space-Challenge)).

## Cómo correrlo

Es HTML/JS estático, sin build ni dependencias de red (React, tipografías e íconos van locales).

```bash
# desde la carpeta del repo
python3 -m http.server 5173 --bind 127.0.0.1
# abre http://127.0.0.1:5173/index.html
```

> **No lo abras con doble clic (`file://`)**: el navegador manda origen `null` y el backend lo bloquea por CORS. Sírvelo en `localhost:5173` o `localhost:3000` (orígenes que el backend ya permite), o móntalo dentro del backend (ver `INTEGRACION_BACKEND.md`).

## Modo en vivo y modo demostración

Al abrir, el front hace `GET /salud` al backend:

- **Backend encendido → modo en vivo.** Tripulación, signos vitales, sueño, cognición y el chat con Orbi salen del backend real. El estado arriba dice "Backend en vivo".
- **Backend apagado → modo demostración.** Usa datos sintéticos para que la interfaz siempre se pueda mostrar. El estado dice "En vivo" (simulado).

Parámetros de URL:

| Parámetro | Efecto |
|---|---|
| `?api=<url>` | Dónde está el backend (por defecto `http://localhost:8000`). |
| `?demo=1` | Fuerza modo demostración (no intenta el backend). |
| `?oscuro=1` | Tema oscuro. |
| `?movimiento=reduced` | Reduce animaciones (accesibilidad). |

## Qué viene del backend (modo en vivo)

| Vista | Endpoint |
|---|---|
| Tripulación (astro_1→Katya, astro_2→José, astro_3→Rodolfo; Carlos = sin sensor, demo) | `GET /tripulantes` |
| Signos vitales en vivo (pulso, SpO₂, presión) | `GET /tripulantes/{id}/salud/stream` (SSE) |
| Rango esperado personal, tendencia, clínico | `GET /tripulantes/{id}/resumen` |
| Aptitud | `GET /tripulantes/{id}/aptitud` |
| Sueño por noche (latencia, duración, eficiencia) | evento `sueno` del stream · `GET …/salud` |
| Cognición (PVT/DSST/Matrix, línea base, 8xxx) | `GET /tripulantes/{id}/cognitivo` |
| Guardar una prueba de reacción (PVT) | `POST /tripulantes/{id}/cognitivo` |
| Chat con Orbi (LLM, streaming + fuentes) | `POST /preguntar/stream` (SSE) |
| Estado del sistema / Orbi disponible | `GET /salud` |

El cliente está en `js/api.js` (todas las llamadas) y `js/live.js` (adapta las respuestas a las vistas). `API_BASE` se configura en la cabecera de `index.html`.

## Estructura

```
index.html          pantallas y lógica (React 18 vía support.js, sin JSX)
css/tokens.css      tokens de diseño (color, estados, tipografía)
css/fonts.css       @font-face locales
css/styles.css      base y animaciones
fonts/              Space Grotesk, Overpass, JetBrains Mono (woff2)
js/api.js           cliente del backend real (fetch + SSE)
js/live.js          adaptador: datos reales → forma que usan las vistas
js/support.js       motor de componentes + React/ReactDOM locales
js/vendor/          react / react-dom (producción)
```

## Notas de integración (pendientes honestos)

- **Modelos personales sin entrenar:** si el backend no corrió `python -m src.series.analizar`, `esperado_personal` llega `null` y el front calcula el rango personal a partir de la serie (fallback). Con los modelos entrenados usa el del backend.
- **Histórico de 15 días:** el backend reproduce 1 día; la vista de "15 días" usa datos sintéticos (marcada como demo). El modo "Hoy · real" sí es el día real.
- **Estados oficiales:** en modo en vivo los colores y etiquetas salen de los códigos del backend: vitales de `/resumen` (2xxx clínico, 3xxx modelo, deriva 4110), panel "Lo que Orbi ve" de `/aptitud` (1xxx, motivos, observaciones, recomendaciones), avisos del evento SSE `notificacion` + `/notificaciones`, y cognición del nivel 8xxx de cada sesión (`/cognitivo`) y del resumen (`/cognitivo/resumen`). La aproximación del cliente solo se usa en modo demostración o mientras llega la primera respuesta. Las inferencias se vuelven a pedir como mucho cada 4 s mientras corre el stream.
- **Sueño:** el rango personal por noche se calcula en el cliente; el nivel clínico del backend lo puede subir (los límites clínicos mandan). Se muestra la medicación registrada.
- **PVT:** la primera sesión de un tripulante se envía con `familiarizacion: true`; el resultado muestra el estado devuelto por el `POST`.
- **Voz:** `js/voz.js` (port de `docs/front/voz.ts`) lee las respuestas del chat oración por oración y las notificaciones (tras la primera interacción del usuario).
- **Estado del sistema:** `GET /salud` cada 8 s; si el backend cae se muestra "sin conexión" y al volver se reconecta el stream. "Reiniciar demo" llama a `POST /tripulantes/reiniciar-simulacion`.
- **Temperatura:** aún no la mide el backend; la vista queda como "próximamente".
- **Carlos N.:** no existe en el backend (identidad de diseño "sin sensor").

Para servir el front desde el propio backend (un solo proceso, sin CORS), ver `INTEGRACION_BACKEND.md`.
