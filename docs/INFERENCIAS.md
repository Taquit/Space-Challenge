# Inferencias del sistema de salud

Documenta cada inferencia que calcula el backend (`src/salud/`) a partir de las lecturas de `data/fisiologico.json`
(`pulso` bpm, `spo2` %, `presion_sistolica` y `presion_diastolica` mmHg, una lectura cada 10 min por tripulante).
Los códigos que aparecen entre paréntesis están en [`CODIGOS.md`](CODIGOS.md).

> Orientativo, **no es diagnóstico médico**. Los rangos clínicos son valores estándar de adulto en reposo y deben ser revisados por personal médico.

> Todos los umbrales numéricos de este documento se configuran en `umbrales.env` (ver [`UMBRALES.md`](UMBRALES.md)); las tablas muestran los valores por defecto.

## Principios

1. **Cada persona tiene su propio modelo.** Por tripulante y por variable hay un modelo entrenado solo con sus datos
   (`models/series/usuarios/<usuario>_<variable>.joblib`, generado con `python -m src.series.analizar`). Predice cada lectura
   a partir de las anteriores (one-step-ahead) y calcula un rango esperado personal.
2. **Los límites clínicos tienen la última palabra.** El modelo responde "¿es raro para esta persona?", no "¿está sano?".
   Nunca puede anular un valor clínicamente peligroso.
3. **Determinista, no generativo.** Todo se calcula en Python; el LLM solo redacta con esos resultados y no inventa cifras.

## Resumen de inferencias

| # | Inferencia | Fuente | Dónde se usa | Archivo |
|---|---|---|---|---|
| 1 | Estadísticas de ventana y tendencia | Lecturas | `/resumen` | `inferencia.py` |
| 2 | Clasificación clínica por límites | Límites absolutos | `/resumen`, `/aptitud`, notificaciones | `referencias.py` |
| 3 | Magnitudes derivadas | Lecturas | `/resumen`, `/aptitud` | `referencias.py`, `inferencia.py` |
| 4 | Desviación respecto al modelo personal | Modelo personal | `/resumen`, `/aptitud`, notificaciones | `analizar.py`, `anomaly_detection.py` |
| 5 | Desviación frente a la línea base | Primeras 15 lecturas | `/resumen` | `inferencia.py` |
| 6 | Deriva lenta | Lecturas | `/aptitud`, notificaciones | `inferencia.py` |
| 7 | Patrones entre variables | Estados + derivadas | `/resumen`, `/aptitud` | `inferencia.py` |
| 8 | Persistencia clínica | Límites + lecturas | `/aptitud` | `inferencia.py` |
| 9 | Línea base no confiable | Línea base + límites | `/aptitud` | `inferencia.py` |
| 10 | Decisión apto / no apto | Todas las anteriores | `/aptitud` | `aptitud.py` |
| 11 | Notificaciones | Clínico + modelo + deriva | `/notificaciones`, SSE | `notificaciones.py` |
| 12 | Sueño (límites, deriva, sostenido) | Resumen por noche | `/resumen`, `/aptitud`, notificaciones | `referencias.py`, `inferencia.py` |
| 13 | Cognitivo (línea base, z de deterioro, persistencia, deriva, patrones) | Sesiones PVT/DSST/Matrix | `/cognitivo/*`, `/resumen`, `/aptitud`, notificaciones, chat | `cognitivo.py` |

## 1. Estadísticas de ventana y tendencia

- **Qué hace:** mínimo, máximo, media, desviación estándar y valor actual sobre las últimas `limite` lecturas (o todo lo transcurrido).
- **Tendencia:** pendiente de la regresión lineal de las últimas 12 lecturas. Es `estable` si `|pendiente| < 0.05 × desviación de la ventana`; si no, `ascendente` o `descendente` (4001/4002/4003).
- **Salida:** `media`, `minimo`, `maximo`, `desviacion`, `tendencia`, `pendiente_por_lectura`, `codigo_tendencia`.

## 2. Clasificación clínica por límites absolutos

Cada valor se compara con límites de referencia (de más grave a menos grave). Códigos 2001 normal, 2002 vigilar, 2010 alerta, 2011 crítico.

| Variable | VIGILAR | ALERTA | CRÍTICO |
|---|---|---|---|
| `pulso` (bpm) | <60 o >100 | <50 o >110 | <40 o >130 |
| `spo2` (%) | <95 | <92 | <90 |
| `presion_sistolica` (mmHg) | ≥130 | <90 o ≥140 | <80 o ≥180 |
| `presion_diastolica` (mmHg) | ≥80 | <60 o ≥90 | <50 o ≥120 |

| `sueno_eficiencia` (%) | <85 | <75 | <65 |
| `sueno_duracion` (h) | <7 | <6 | <5 |
| `sueno_latencia` (min) | >30 | >45 | >60 |

Las filas de sueño evalúan **una noche** por lectura (ver "Sueño" abajo). Cada nivel trae una etiqueta (`bradicardia`, `taquicardia`, `hipoxemia`, `hipotensión`, `hipertensión`, `crisis hipertensiva`...) en `interpretacion_clinica`.

## 3. Magnitudes derivadas

Se calculan con los últimos valores de cada variable.

| Magnitud | Fórmula | Rango normal | Hallazgo si se sale |
|---|---|---|---|
| Presión de pulso | sistólica − diastólica | 25-60 mmHg (típico 30-50) | 5009 |
| Presión arterial media (PAM) | diastólica + (sistólica − diastólica)/3 | 70-100 mmHg | solo informativa |
| Índice de choque | pulso / sistólica | < 0.9 | 5008 |

## 4. Desviación respecto al modelo personal

- **Qué hace:** el modelo del tripulante predice cada lectura con las anteriores y el detector de anomalías compara el valor real con el esperado.
- **Rango esperado:** `predicción ± 2σ`, con σ de los residuos propios de esa persona.
- **Clasificación por z-score del residuo:**
  - `|z| ≥ 2` → ADVERTENCIA (3002)
  - `|z| ≥ 3`, o `|z| ≥ 2.5` junto con una marca de Isolation Forest → ANOMALIA (3010)
  - en otro caso → NORMAL (3001); sin modelo → 3000.
- **Variables:** pulso, SpO2, presión sistólica y diastólica (un modelo por cada una).
- **Límite conocido:** al predecir con las lecturas previas, un cambio lento y constante lo "sigue" y no se marca. Eso lo cubre la deriva (#6) y los límites clínicos (#2, #8).
- **Salida:** `estado_modelo`, `esperado_personal {valor, lower, upper}`, `advertencias_ventana`, `anomalias_ventana`, `modelo`.

## 5. Desviación frente a la línea base personal

- **Línea base:** media de las primeras 15 lecturas del tripulante.
- **Salida:** `linea_base`, `diferencia_base` (actual − base) y `z_base` (diferencia / desviación de esas 15 lecturas).

## 6. Deriva lenta

Detecta cambios acumulados que el modelo no ve porque cada paso es pequeño (código 4110 detectada, 4101 sin deriva).

- Promedia las últimas 6 lecturas y las compara con (a) la línea base y (b) el promedio de hace ~36 lecturas (~6 h). Toma la mayor diferencia.
- Hay deriva si `|cambio| ≥ max(umbral de la variable, 2σ de la línea base)`.
- Umbrales: pulso 8 bpm, SpO2 2 %, sistólica 10 mmHg, diastólica 6 mmHg.
- Necesita al menos 21 lecturas.
- **Efecto:** observación (5005); si además el valor ya está fuera de rango clínico, es motivo de no apto.

## 7. Patrones entre variables

Combina el estado del modelo personal con los valores actuales.

| Patrón | Condición | Código | Efecto |
|---|---|---|---|
| Compromiso respiratorio | SpO2 < 95 y pulso desviado en su modelo | 5004 | No apto |
| Alteración circulatoria | Sistólica y pulso desviados a la vez | 5007 | Observación |
| Índice de choque elevado | pulso/sistólica > 0.9 | 5008 | Observación |
| Presión de pulso anormal | fuera de 25-60 mmHg | 5009 | Observación |
| Múltiples desviaciones | ≥ 3 variables desviadas a la vez | 5011 | Observación |

## 8. Persistencia clínica

Una alerta clínica (nivel ≥ ALERTA) cuenta como **sostenida** si las últimas 3 lecturas (~30 min) la cumplen, **sin depender del modelo**. Evita falsos positivos de una lectura aislada y evita que el modelo oculte un problema real.

## 9. Línea base no confiable

Si la media de la línea base de una persona ya está en nivel ≥ ALERTA clínica, el modelo personal aprendió un estado no sano como "normal" (por ejemplo, empezó el día enfermo). Se marca (5006) y manda el criterio clínico. Un nivel solo VIGILAR (por ejemplo pulso de reposo de 59 bpm) no cuenta.

## 10. Decisión apto / no apto

| Resultado | Código | Condiciones |
|---|---|---|
| Crítico, no apto | 1011 | Alguna medida en nivel crítico (5001) |
| Riesgo, no apto | 1010 | Alerta clínica sostenida (5002); alerta clínica + fuera de su patrón (5003); anomalía personal + fuera de rango (5015); deriva con el valor ya fuera de rango (5005); patrón respiratorio (5004) |
| Apto con seguimiento | 1002 | Solo observaciones: fuera de rango leve (5012), alerta puntual (5010), desviación leve o anomalía dentro de rango clínico (5014/5013), deriva con valor aún normal, línea base no confiable (5006), otros patrones |
| Saludable | 1001 | Sin motivos ni observaciones |

Se devuelven `motivos` (por qué no es apto), `observaciones`, `recomendaciones` y las `derivadas`.

## 11. Notificaciones

Se generan al **empeorar** el estado de una medida, sin repetir el mismo nivel.

- **Por nivel:** severidad = la mayor entre el nivel clínico y el del modelo (ADVERTENCIA→VIGILAR, ANOMALIA→ALERTA). Códigos 6001 vigilar, 6010 alerta, 6011 crítico.
- **Un fuera de rango leve (VIGILAR) que el modelo ve normal para esa persona no notifica.**
- **Por deriva (6020):** una vez al detectarse; se rearma tras 12 lecturas seguidas sin deriva.
- **Entrega:** `GET /tripulantes/{id}/notificaciones?desde=<id>` y evento SSE `notificacion`. Se guardan en `data/resultados/notificaciones.json`.

## 12. Sueño

Fuente: `data/sueno.json` (resumen por noche del estudio BRSM; se genera con `python scripts/importar_sueno.py`). Variables `sueno_latencia`, `sueno_duracion`, `sueno_eficiencia`.

- **Sin modelo personal:** son pocas noches (69 y 6) y no una serie a 10 min. `estado_modelo = SIN_MODELO`; se usan límites clínicos (§2), estadísticas, tendencia y deriva lenta (ventana en noches, umbrales `DERIVA_UMBRAL_SUENO_*`).
- **Sueño deficiente sostenido (5017):** duración o eficiencia en alerta clínica las últimas 3 noches.
- **Solo observa:** el sueño nunca declara *no apto* por sí solo; añade la observación 5016 (valor fuera de rango) o 5017 y sube el nivel a VIGILAR.
- **Notificaciones:** por límite clínico (≥ ALERTA) y por deriva lenta, igual que el resto. Un VIGILAR aislado no notifica.
- **Medicación:** la medicación registrada esa noche (`Comments`) viaja en la lectura de sueño y en el contexto del chat.
- **Aviso:** los límites de sueño son orientativos; no hay un estándar único y los datos vienen de un estudio de reposo en cama.

## 13. Cognitivo

Fuente: `data/cognitivo.json` (sesiones de PVT, DSST y Matrix Reasoning; simuladas con `python scripts/simular_cognitivo.py`, o enviadas con `POST /tripulantes/{id}/cognitivo`). Plan y fundamento en [`COGNITIVO.md`](COGNITIVO.md). Código en `src/salud/cognitivo.py`.

- **Cada persona es su referencia.** Métricas: `cog_pvt_rt` y `cog_pvt_lapsos` (deterioro si **suben**), `cog_dsst_throughput` y `cog_matrix_correctas` (deterioro si **bajan**).
- **Línea base:** media y desviación de las primeras 3 sesiones **sin contar la de familiarización** (que se descarta). Con menos: `SIN_LINEA_BASE` (8000), no se evalúa nada. La desviación tiene piso `max(sd, 5 % de la media)` (y 1 como mínimo en métricas de conteo: lapsos y correctas de Matrix) para evitar z explosivos con pocas sesiones.
- **z de deterioro** (positivo = peor que su base): `(valor − media)/sd_efectiva` si sube, `(media − valor)/sd_efectiva` si baja. `z < 1.5` NORMAL (8001) · `1.5 ≤ z < 2` VIGILAR (8002) · `z ≥ 2` ALERTA (8010). El nivel de la sesión es el peor de sus métricas; el estado del usuario es el de su última sesión evaluada.
- **ALERTA sostenida:** ALERTA en las últimas 2 sesiones. Una ALERTA aislada se trata como "repetir la prueba", no como hallazgo.
- **Deriva lenta (4110 / 4101):** promedio del z de las últimas 4 sesiones ≥ 1.0 en alguna métrica y con la mayoría de esas sesiones en z ≥ 0.5 (una sesión atípica aislada no cuenta). Requiere 3 + 4 sesiones válidas. Una caída súbita que dura varias sesiones también se ve como deriva.
- **Patrones (observaciones):** 5018 nivel cognitivo ≥ VIGILAR · 5019 con sueño deficiente sostenido (5017; se usa el sueño más reciente disponible) · 5020 con alguna medida fisiológica desviada o fuera de rango. Deriva: 5005 con variable `cognitivo`.
- **Solo observa:** nunca produce 1010 ni 1011. Con 5018-5020 el resultado es "Apto con seguimiento" (1002) y la recomendación es repetir la sesión, descartar fatiga, distracción o poco esfuerzo, y revisar sueño y signos vitales.
- **Notificaciones:** ALERTA sostenida → 6010; deriva → 6020 (variable `cognitivo`). Una vez cada una; se rearman al desaparecer. VIGILAR o ALERTA aislada no notifican.
- **Orientativo:** las pruebas son versiones propias con el mismo paradigma que las de la literatura; sus propiedades psicométricas no están validadas.

## Uso en el chat

`POST /preguntar` y `/preguntar/stream` con `usuario` (y `variables` opcional) inyectan al LLM un resumen con las inferencias #1-#10 y #13 (cognitivo, si hay sesiones) de esa persona. El LLM las redacta en lenguaje natural, cita solo cifras dadas e indica si es apto o no.

## Limitaciones

- Cada modelo se entrena con un solo día (~144 lecturas por persona); la línea base sale de las primeras 15 lecturas.
- No hay `actigraphy_activity` en los signos vitales: no se distingue ejercicio de estrés. El sueño sí viene de actigrafía, pero como resumen nocturno.
- El sueño no se cruza con los signos vitales por fecha (son de épocas distintas); solo se muestra junto a ellos.
- Los límites clínicos son de adulto en reposo; en microgravedad o durante actividad pueden ser distintos.
- Las lecturas son una reproducción simulada de datos grabados (`src/datos/salud.py`).
- Cognitivo: sin normas poblacionales, solo se compara contra uno mismo (la línea base debe completarse antes); pocas sesiones hacen inestable la desviación; el efecto de práctica difiere por prueba; se asume el mismo equipo en todas las sesiones. Las sesiones no se reproducen en el tiempo simulado: se leen completas.
