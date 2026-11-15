# Pruebas cognitivas: plan de integración

Plan para añadir monitoreo cognitivo al sistema de salud (`src/salud/`). Está escrito para ejecutarse por fases con Claude Code y para vivir en el repo como documentación.

> Orientativo, **no es diagnóstico médico**. Los umbrales de este documento son valores por defecto **propuestos** y deben ser revisados antes de usarse como criterio real.

## 1. Objetivo

Añadir un módulo de pruebas cognitivas breves (3 pruebas, 5 a 7 min por sesión) cuyos resultados se interpretan **contra la línea base de cada persona** y se cruzan con las inferencias existentes (signos vitales y sueño). Todo local, sin internet y sin dependencias nuevas.

## 2. Fundamento (fuentes)

| Fuente | Qué aporta |
|---|---|
| Basner et al. 2015, *Development and Validation of the Cognition Test Battery for Spaceflight* (Aerosp Med Hum Perform 86:942-952) | Batería de 10 pruebas (~17.8 min). Tras una noche sin dormir, solo tres mostraron efectos medios o grandes: PVT (d=1.00), DSST (d=0.68) y Matrix Reasoning (d=0.65). Muestra efectos de práctica distintos por prueba. |
| Basner, *Individualized Real-Time Neurocognitive Assessment Toolkit for Space Flight* (simposio CSA/ESA/JAXA/NASA, incrementos 41 y 42) | Protocolo en la ISS: 1 familiarización, 3 líneas base, 11 sesiones en vuelo cada 2-4 semanas, 3 posvuelo. Puntajes estandarizados frente a percentiles. Administración flexible. |
| Kane et al. 2005, *Development and Validation of WinSCAT* (Aviat Space Environ Med 76(6, Suppl.):B183-91) | WinSCAT: 5 pruebas, máximo 15 min, repetible. Métrica principal: *throughput* (respuestas correctas por unidad de tiempo). |
| Kane, Seaton y Sipes 2011, *Cognitive Assessment During Long-Duration Space Flight* | Protocolo: 6 sesiones de línea base, 1 al mes en vuelo, 1 posvuelo. Línea base móvil, reglas de cambio (índice de cambio confiable, regresión, frecuencia normativa). En 172 sesiones en la ISS, 92% fueron nominales; las atípicas se atribuyeron sobre todo a fatiga, distracción o poco esfuerzo. |

## 3. Principios (heredados de `docs/INFERENCIAS.md`)

1. **Cada persona es su propia referencia.** No hay límites clínicos absolutos para cognición; se compara contra su línea base.
2. **Determinista, no generativo.** Todo se calcula en Python; el LLM solo redacta con los resultados.
3. **Solo observa.** Como el sueño, una caída cognitiva nunca declara *no apto* por sí sola. Añade observaciones y sube el nivel hasta VIGILAR. Razón: las sesiones atípicas suelen tener causas no cognitivas (fatiga, distracción, poco esfuerzo).
4. **Umbrales sin tocar código.** Todo en `umbrales.env` con prefijo `COG_`.
5. **No copiar pruebas propietarias.** Las pruebas originales (Penn CNB, Pulsar Informatics, ANAM) tienen licencia. Se implementan versiones propias con el mismo paradigma, con estímulos generados por algoritmo. No usar fotografías de actores.

## 4. Alcance

**Incluye (v1):** PVT, DSST y Matrix Reasoning; almacenamiento de sesiones; inferencias (#13 en `docs/INFERENCIAS.md`); integración con `/aptitud`, `/resumen`, notificaciones y chat; datos simulados.

**No incluye (v1):** BART, Line Orientation, Emotion Recognition, Visual Object Learning, Abstract Matching, normas poblacionales, modelo de series de tiempo por persona (hay pocas sesiones).

## 5. Pruebas

Las pruebas corren en el frontend (el tiempo de reacción se mide en el navegador con `performance.now()`); el backend recibe métricas ya calculadas y los datos crudos.

### 5.1 PVT (atención sostenida)
- Estímulo tras intervalo aleatorio de 2 a 10 s; el usuario responde con un clic o tecla.
- Duración propuesta: 3 min (el paper usa ~3.2 min); se puede reducir a 1 o 2 min.
- Métricas: `rt_media_ms`, `rt_mediana_ms`, `lapsos` (respuestas > 500 ms, convención estándar del PVT), `falsos_inicios` (respuestas antes del estímulo), `n_estimulos`.
- Dirección del deterioro: **sube** `rt_media_ms` y `lapsos`.

### 5.2 DSST (velocidad de procesamiento)
- Clave de 9 pares dígito-símbolo; aparece un símbolo y se elige su número. Duración fija: 90 s.
- La clave se reasigna al azar en cada sesión (semilla guardada en `forma`).
- Métricas: `correctas`, `intentos`, `precision`, `throughput` (correctas / segundo), `rt_media_ms`.
- Dirección del deterioro: **baja** `throughput` y `precision`.

### 5.3 Matrix Reasoning (razonamiento abstracto)
- 12 ítems de matriz 3×3 con una celda faltante y varias opciones; se detiene tras 3 errores seguidos.
- Los ítems se generan con reglas (por ejemplo, progresión de forma, color o cantidad) a partir de una semilla, para tener formas alternativas.
- Métricas: `correctas`, `intentos`, `precision`, `tiempo_total_s`, `throughput`.
- Dirección del deterioro: **baja** `correctas` y `throughput`.
- Si el generador de ítems resulta demasiado costoso, sustituir por un N-back con estímulos generados algorítmicamente (`2-back`, 62 estímulos como en el paper).

## 6. Modelo de datos

Archivo: `data/cognitivo.json` (mismo estilo que `data/sueno.json`).

```json
{
  "usuario": "u01",
  "sesiones": [
    {
      "id": 1,
      "fecha": "2026-11-15T09:30:00-06:00",
      "forma": "A",
      "semilla": 1234,
      "familiarizacion": true,
      "pruebas": {
        "pvt":    {"rt_media_ms": 281.4, "rt_mediana_ms": 270.0, "lapsos": 1, "falsos_inicios": 0, "n_estimulos": 24},
        "dsst":   {"correctas": 42, "intentos": 44, "precision": 0.955, "throughput": 0.467, "rt_media_ms": 2050.0},
        "matrix": {"correctas": 8, "intentos": 12, "precision": 0.667, "tiempo_total_s": 143.2, "throughput": 0.056}
      },
      "contexto": {"comentario": ""}
    }
  ]
}
```

Reglas:
- Guardar siempre las métricas crudas; las inferencias se recalculan al leer.
- `familiarizacion: true` marca la sesión que se **descarta** de la línea base (el efecto de práctica es mayor al principio).
- `contexto` es opcional (por ejemplo, si el usuario indica fatiga o distracción durante la prueba).

## 7. Inferencias (nueva sección #13 de `docs/INFERENCIAS.md`)

### 7.1 Métricas evaluadas

| Clave | Prueba | Métrica | Deterioro si |
|---|---|---|---|
| `cog_pvt_rt` | PVT | `rt_media_ms` | sube |
| `cog_pvt_lapsos` | PVT | `lapsos` | sube |
| `cog_dsst_throughput` | DSST | `throughput` | baja |
| `cog_matrix_correctas` | Matrix | `correctas` | baja |

### 7.2 Línea base
- Media y desviación de las primeras `COG_BASELINE_SESIONES` sesiones **sin contar** la de familiarización.
- Hasta completarla: `estado_cognitivo = SIN_LINEA_BASE` (código 8000); no se evalúa nada.
- Con pocas sesiones la desviación es inestable. Se usa `sd_efectiva = max(sd_base, COG_SD_MIN_REL × media_base)` para evitar z-scores explosivos.
- Para métricas de conteo (`lapsos`, `correctas` de Matrix) el piso absoluto es `COG_SD_MIN_ABS_CONTEO`, porque su media base suele ser cercana a 0.
- Opcional en una fase posterior: línea base móvil (como WinSCAT) con las últimas `COG_BASELINE_MOVIL` sesiones nominales.

### 7.3 Desviación (z de deterioro)
`z_deterioro = (valor − media_base) / sd_efectiva` si el deterioro es "sube", o `(media_base − valor) / sd_efectiva` si es "baja". Positivo = peor que su base.

| Condición | Nivel | Código |
|---|---|---|
| `z_deterioro < COG_Z_VIGILAR` | NORMAL | 8001 |
| `COG_Z_VIGILAR ≤ z < COG_Z_ALERTA` | VIGILAR | 8002 |
| `z ≥ COG_Z_ALERTA` | ALERTA | 8010 |

El nivel cognitivo global de la sesión es el peor de sus métricas.

### 7.4 Persistencia
Una ALERTA cuenta como **sostenida** si se cumple en las últimas `COG_PERSISTENCIA_SESIONES` sesiones. Una sesión aislada se trata como "repetir la prueba" (como WinSCAT), no como hallazgo.

### 7.5 Deriva lenta
Promedio de las últimas `COG_DERIVA_VENTANA` sesiones frente a la línea base. Hay deriva si el `z` promedio ≥ `COG_DERIVA_Z` en alguna métrica **y** la mayoría de esas sesiones tienen `z ≥ COG_DERIVA_Z/2` (así una sesión atípica aislada no cuenta; una caída súbita que dura varias sesiones también se ve como deriva). Reutiliza los códigos existentes 4110 (`DERIVA_LENTA`) y 4101 (`SIN_DERIVA`), y la observación 5005 con la variable `cognitivo`. Requiere al menos `COG_BASELINE_SESIONES + COG_DERIVA_VENTANA` sesiones.

### 7.6 Patrones entre variables

| Patrón | Condición | Código | Efecto |
|---|---|---|---|
| Rendimiento cognitivo reducido | Nivel cognitivo ≥ VIGILAR | 5018 | Observación |
| Sueño deficiente + caída cognitiva | Sueño deficiente sostenido (5017) y nivel cognitivo ≥ VIGILAR | 5019 | Observación |
| Fisiología + caída cognitiva | Alguna medida fisiológica desviada o fuera de rango y nivel cognitivo ≥ VIGILAR | 5020 | Observación |

El cruce de sueño con vitales tiene la limitación ya documentada (fechas distintas). Para el patrón 5019 se usa el sueño más reciente disponible para ese usuario y se indica en la salida.

### 7.7 Efecto en la decisión (#10)
- Nunca produce 1010 ni 1011.
- Con observación 5018/5019/5020, el resultado pasa a "Apto con seguimiento" (1002).
- La recomendación sugerida: repetir la sesión, descartar causas no cognitivas (fatiga, distracción, esfuerzo), y revisar sueño y signos vitales.

### 7.8 Notificaciones
- Por ALERTA sostenida (7.4) o deriva (7.5). Un VIGILAR o una ALERTA aislada no notifica.
- Se reutilizan los códigos existentes 6010 (`NOTIF_ALERTA`) y 6020 (`NOTIF_DERIVA`) con la variable `cognitivo`.

### 7.9 Códigos nuevos (para pegar en `docs/CODIGOS.md`)

Verificados contra el catálogo actual. Se añade la familia 8xxx (7xxx es del chat) y se reutilizan 4101/4110, 6010 y 6020.

| Familia | Código | Nombre | Significado |
|---|---|---|---|
| 8xxx · Nivel cognitivo | 8000 | `COG_SIN_LINEA_BASE` | Aún no hay sesiones de línea base suficientes. |
| | 8001 | `COG_NORMAL` | Rendimiento dentro de lo habitual para esta persona. |
| | 8002 | `COG_VIGILAR` | Rendimiento algo peor que su línea base. |
| | 8010 | `COG_ALERTA` | Rendimiento claramente peor que su línea base. |
| 5xxx · Hallazgos | 5018 | `RENDIMIENTO_COGNITIVO_REDUCIDO` | Nivel cognitivo en VIGILAR o peor (observación). |
| | 5019 | `SUENO_Y_COGNICION` | Sueño deficiente sostenido junto con caída cognitiva. |
| | 5020 | `FISIOLOGIA_Y_COGNICION` | Desviación fisiológica junto con caída cognitiva. |
| 9xxx · Errores | 9004 | `SESION_COGNITIVA_INVALIDA` | La sesión enviada no cumple el esquema. |

También añadir 8xxx a la tabla "Dónde aparece cada código" (`cognitivo.codigo_nivel` en `/resumen`).

## 8. Umbrales propuestos (`umbrales.env`)

| Clave | Valor por defecto | Descripción |
|---|---|---|
| `COG_BASELINE_SESIONES` | 3 | Sesiones de línea base (sin contar familiarización). WinSCAT usa 6; Cognition usa 3 |
| `COG_SD_MIN_REL` | 0.05 | Piso de la desviación como fracción de la media |
| `COG_SD_MIN_ABS_CONTEO` | 1 | Piso absoluto de la desviación para métricas de conteo (añadido en la implementación) |
| `COG_Z_VIGILAR` | 1.5 | z de deterioro para VIGILAR |
| `COG_Z_ALERTA` | 2.0 | z de deterioro para ALERTA |
| `COG_PERSISTENCIA_SESIONES` | 2 | Sesiones seguidas para ALERTA sostenida |
| `COG_DERIVA_VENTANA` | 4 | Sesiones promediadas para la deriva |
| `COG_DERIVA_Z` | 1.0 | z promedio mínimo para deriva |
| `COG_PVT_LAPSO_MS` | 500 | Umbral de lapso del PVT |

Estos valores no salen de los papers; son un punto de partida razonable y deben ajustarse con datos reales o con asesoría médica/psicométrica.

## 9. API

Siguiendo el estilo de rutas existente (`/tripulantes/{id}/...`):

| Método | Ruta | Función |
|---|---|---|
| `POST` | `/tripulantes/{id}/cognitivo` | Guarda una sesión (valida el esquema de la sección 6) |
| `GET` | `/tripulantes/{id}/cognitivo` | Historial de sesiones y su evaluación |
| `GET` | `/tripulantes/{id}/cognitivo/resumen` | Línea base, estado, deriva y observaciones |

Errores: sesión inválida → 9004 (`SESION_COGNITIVA_INVALIDA`); usuario inexistente → 9001. En `/resumen` el bloque cognitivo lleva `cognitivo.codigo_nivel` (8xxx).

Además: bloque cognitivo en `/resumen` y `/aptitud`, y en el contexto del chat (`/preguntar`) con cifras ya calculadas.

## 10. Archivos a crear o modificar

Estructura real del repo (`src/api`, `src/datos`, `src/salud`, `tests`, `docs`, `scripts`, `data`). Los usuarios existentes son `astro_1`, `astro_2` y `astro_3`.

| Archivo | Acción |
|---|---|
| `src/salud/cognitivo.py` | Nuevo: línea base, z de deterioro, persistencia, deriva, patrones |
| `src/datos/cognitivo.py` | Nuevo: lectura y escritura de `data/cognitivo.json` (mismo estilo que `src/datos/salud.py`) |
| `data/cognitivo.json` | Nuevo: sesiones por usuario (generado por el simulador) |
| `src/salud/codigos.py` | Añadir los códigos de 7.9 (8xxx, 5018-5020, 9004) |
| `src/salud/umbrales.py` | Añadir claves `COG_*` a `DEFAULTS` |
| `umbrales.env` | Añadir claves `COG_*` con comentario de unidad |
| `src/salud/aptitud.py` | Integrar observaciones 5018-5020 (sin producir 1010 ni 1011) |
| `src/salud/notificaciones.py` | Notificaciones por alerta sostenida y deriva cognitiva |
| `src/api/salud.py` | Rutas de la sección 9 y bloque cognitivo en `/resumen` y `/aptitud` |
| `src/api/sse.py` | Revisar si el evento `notificacion` necesita cambios (probablemente no) |
| `src/api/main.py` | Solo si hay que registrar algo nuevo |
| Contexto del chat | Añadir el bloque cognitivo al resumen que se inyecta al LLM; revisar `src/api/salud.py` y `src/rag/agente.py` para ubicar dónde se arma |
| `scripts/simular_cognitivo.py` | Nuevo: genera sesiones para `astro_1` (estable), `astro_2` (caída súbita) y `astro_3` (deriva lenta) |
| `docs/INFERENCIAS.md` | Añadir sección #13 y la fila en el resumen de inferencias |
| `docs/UMBRALES.md` | Añadir el grupo "Cognitivo" |
| `docs/CODIGOS.md` | Añadir la familia 8xxx y la fila en "Dónde aparece cada código" |
| `docs/API.md` y `docs/openapi.json` | Documentar las rutas nuevas (regenerar `openapi.json` con el procedimiento actual del repo) |
| `docs/FRONT.md` | Contrato para el frontend: formato de la sesión y campos del bloque cognitivo |
| `tests/test_cognitivo.py` | Nuevo: pruebas de la sección 12 (junto a `tests/test_salud.py`) |

El repo no contiene código de frontend (solo `docs/FRONT.md` y `docs/front/voz.ts`), así que las pruebas en pantalla se implementan en el proyecto del front a partir del contrato de `docs/FRONT.md`.

## 11. Fases

Cada fase debe dejar el sistema funcionando y con pruebas pasando.

**Fase 1: datos y simulación**
- Esquema JSON, `src/datos/cognitivo.py` y `scripts/simular_cognitivo.py`.
- Criterio de aceptación: el script genera sesiones para `astro_1` (estable), `astro_2` (caída súbita) y `astro_3` (deriva lenta).

**Fase 2: inferencia**
- `src/salud/cognitivo.py`, umbrales `COG_*` y códigos nuevos.
- Criterio: con los datos simulados, el estable da NORMAL (8001), la caída da VIGILAR/ALERTA (8002/8010) y la deriva da 4110. Con menos sesiones que la línea base, devuelve `SIN_LINEA_BASE`.

**Fase 3: integración con aptitud, resumen y notificaciones**
- Patrones 5018-5020, efecto en `/aptitud`, notificaciones.
- Criterio: el módulo cognitivo nunca produce 1010 ni 1011; no cambia el resultado de los usuarios sin datos cognitivos.

**Fase 4: API y chat**
- Rutas de la sección 9 y bloque en el contexto del LLM.
- Criterio: `/preguntar` cita solo cifras presentes en el bloque cognitivo y deja claro que es orientativo.

**Fase 5: contrato y frontend**
- Documentar en `docs/FRONT.md` el formato de sesión y los campos de resultado. Implementar en el proyecto del front, en este orden: PVT → DSST → Matrix, con envío por `POST`.
- Criterio: una sesión completa hecha en pantalla se guarda en `data/cognitivo.json` y aparece en `GET /tripulantes/{id}/cognitivo`.

**Fase 6: ajustes**
- Formas alternativas adicionales, línea base móvil, puntaje compuesto ponderado por *throughput* y pruebas extra (BART, N-back).

## 12. Pruebas automáticas mínimas

- Línea base: la sesión de familiarización se excluye; con menos de `COG_BASELINE_SESIONES` sesiones, estado `SIN_LINEA_BASE`.
- z de deterioro con el signo correcto para métricas que "suben" y las que "bajan".
- Piso de desviación: base con desviación 0 no produce z infinito.
- Persistencia: una ALERTA aislada no notifica; dos seguidas sí.
- Deriva: se detecta con caída gradual y no con una sesión atípica aislada.
- Regresión: `/aptitud` es idéntico al actual para usuarios sin sesiones cognitivas.
- Seguridad: ninguna combinación de entradas cognitivas produce 1010 o 1011.

## 13. Limitaciones

- Sin normas poblacionales offline: solo se compara contra uno mismo, así que la línea base debe completarse antes de interpretar.
- Pocas sesiones por persona: las estimaciones de desviación son inestables (por eso el piso `COG_SD_MIN_REL`).
- Efecto de práctica: distinto en cada prueba según el paper; las formas alternativas lo reducen pero no lo eliminan.
- Medición en navegador: la latencia de pantalla y entrada afecta los tiempos de reacción; se asume el mismo equipo en todas las sesiones.
- Causas no cognitivas: fatiga, distracción y esfuerzo pueden explicar una sesión atípica (así lo reportan los datos de la ISS), de ahí que el módulo solo observe.
- El sueño y los vitales vienen de épocas distintas (limitación existente).
- Las pruebas son versiones propias, no las originales: sus propiedades psicométricas no están validadas.

## 14. Instrucciones para Claude Code

Antes de empezar:
1. Leer `docs/INFERENCIAS.md`, `docs/UMBRALES.md`, `docs/CODIGOS.md` y `docs/BACKEND.md`, y revisar `src/salud/` (en especial `codigos.py`, `umbrales.py` y `aptitud.py`) y `src/api/salud.py` para seguir su convención.
2. Usar los códigos de 7.9. Ya se verificaron contra `docs/CODIGOS.md`: 7xxx está ocupado por el chat, por eso lo cognitivo usa 8xxx. Si el catálogo cambió, volver a comprobarlo.
3. No añadir dependencias nuevas. No modificar el comportamiento existente sin pruebas de regresión.
4. Trabajar una fase por vez; al terminar cada una, ejecutar las pruebas y actualizar `docs/INFERENCIAS.md`, `docs/UMBRALES.md` y `docs/CODIGOS.md`.

Prompt sugerido para cada fase:

> Lee `docs/COGNITIVO.md` y ejecuta la **Fase N**. Sigue la convención del repo, no agregues dependencias, escribe las pruebas de la sección 12 que correspondan y actualiza la documentación afectada. Al terminar resume qué cambió y qué quedó pendiente.

## 15. Estado de la implementación

Fases 1-4 implementadas, más el contrato de la fase 5 en `docs/FRONT.md` §9. Pendientes: las pruebas en pantalla (el front vive fuera de este repo) y la fase 6. El contexto del chat se arma en `src/api/main.py` (`contexto_fisio`) y `src/rag/agente.py` (`estado_fisiologico`). Las sesiones sí se pueden enviar solo con alguna prueba (mínimo una).

## 16. Preguntas abiertas

- ¿El frontend vive en otro repo o carpeta? Define dónde se implementan las pruebas en pantalla.
- ¿Se dispone de tiempo para las tres pruebas en el frontend, o se entrega la v1 con datos simulados y solo PVT?
