# Códigos de respuesta

Todas las respuestas del backend de salud llevan un `codigo` numérico para que el front decida colores, iconos y textos sin interpretar cadenas. `GET /tripulantes/codigos` devuelve este mismo catálogo.

> Orientativo, **no es diagnóstico médico**. Los límites clínicos tienen la última palabra: el modelo personal ("¿es raro para esta persona?") nunca anula un valor clínicamente peligroso.

## Dónde aparece cada código

| Campo | Endpoint | Familia |
|---|---|---|
| `codigo`, `estado` | `GET /tripulantes/{id}/aptitud` | 1xxx |
| `motivos[].codigo`, `observaciones[].codigo` | `/aptitud` | 5xxx |
| `medidas.<var>.codigo_nivel_clinico` | `GET /tripulantes/{id}/resumen` | 2xxx |
| `medidas.<var>.codigo_estado_modelo` | `/resumen` | 3xxx |
| `medidas.<var>.codigo_tendencia`, `medidas.<var>.deriva.codigo` | `/resumen` | 4xxx |
| `patrones[].codigo` | `/resumen` | 5xxx |
| `codigo`, `tipo` | `GET /tripulantes/{id}/notificaciones` y evento SSE `notificacion` | 6xxx |
| `codigo` | `POST /preguntar` | 7xxx |
| `detail.codigo` | cualquier error HTTP (404/503) | 9xxx |

## Catálogo

### 1xxx · Estado general del tripulante (`/aptitud`)

| Código | Nombre | Significado |
|---|---|---|
| 1001 | `SALUDABLE` | Apto, sin hallazgos. |
| 1002 | `APTO_CON_SEGUIMIENTO` | Apto, pero con observaciones que conviene vigilar. |
| 1010 | `RIESGO` | No apto: hay un riesgo que requiere reposo y reevaluación. |
| 1011 | `CRITICO` | No apto: valor en rango crítico, atención inmediata. |

### 2xxx · Nivel clínico de una medida (límite absoluto)

| Código | Nombre | Significado |
|---|---|---|
| 2001 | `CLINICO_NORMAL` | Valor dentro del rango clínico de referencia. |
| 2002 | `CLINICO_VIGILAR` | Valor ligeramente fuera del rango. |
| 2010 | `CLINICO_ALERTA` | Valor claramente fuera del rango. |
| 2011 | `CLINICO_CRITICO` | Valor en rango crítico. |

### 3xxx · Estado según el modelo personal

| Código | Nombre | Significado |
|---|---|---|
| 3000 | `MODELO_NO_DISPONIBLE` | Sin modelo personal para esta medida. |
| 3001 | `MODELO_NORMAL` | Normal para esta persona según su modelo. |
| 3002 | `MODELO_ADVERTENCIA` | Desviación leve (≥2σ) de su patrón personal. |
| 3010 | `MODELO_ANOMALIA` | Desviación fuerte (≥3σ) de su patrón personal. |

### 4xxx · Tendencia y deriva

| Código | Nombre | Significado |
|---|---|---|
| 4001 | `TENDENCIA_ESTABLE` | La medida se mantiene estable. |
| 4002 | `TENDENCIA_ASCENDENTE` | La medida sube de forma sostenida. |
| 4003 | `TENDENCIA_DESCENDENTE` | La medida baja de forma sostenida. |
| 4101 | `SIN_DERIVA` | Sin cambio acumulado relevante. |
| 4110 | `DERIVA_LENTA` | Cambio acumulado lento pero relevante, aunque cada lectura parezca normal. |

### 5xxx · Hallazgos: motivos de *no apto* y observaciones

| Código | Nombre | Significado |
|---|---|---|
| 5001 | `LIMITE_CRITICO` | Medida en rango crítico. |
| 5002 | `ALERTA_CLINICA_SOSTENIDA` | Medida en alerta clínica durante varias lecturas seguidas. |
| 5003 | `ALERTA_CLINICA_Y_MODELO` | Medida en alerta clínica y fuera de su patrón personal. |
| 5004 | `PATRON_RESPIRATORIO` | SpO2 baja junto con pulso fuera de su patrón: posible compromiso respiratorio. |
| 5005 | `DERIVA_LENTA_HALLAZGO` | Deriva lenta de la medida (con valor ya fuera de lo normal si es motivo). |
| 5006 | `LINEA_BASE_NO_CONFIABLE` | La línea base ya estaba fuera de rango clínico; manda el criterio clínico. |
| 5007 | `PATRON_CIRCULATORIO` | Presión sistólica y pulso desviados a la vez. |
| 5008 | `INDICE_CHOQUE_ELEVADO` | Índice de choque (pulso/sistólica) > 0.9. |
| 5009 | `PRESION_PULSO_ANORMAL` | Presión de pulso fuera de 25-60 mmHg. |
| 5010 | `ALERTA_PUNTUAL` | Una lectura en alerta clínica, aún no sostenida. |
| 5011 | `MULTIPLES_DESVIACIONES` | Tres o más variables fuera de su patrón a la vez. |
| 5012 | `FUERA_DE_RANGO_LEVE` | Valor ligeramente fuera del rango clínico. |
| 5013 | `ANOMALIA_PERSONAL` | Anomalía respecto a su modelo, pero dentro del rango clínico. |
| 5014 | `DESVIACION_PERSONAL_LEVE` | Desviación leve de su patrón personal. |
| 5015 | `ANOMALIA_Y_FUERA_DE_RANGO` | Anomalía personal y además fuera de rango clínico. |

### 6xxx · Notificaciones

| Código | Nombre | Significado |
|---|---|---|
| 6001 | `NOTIF_VIGILAR` | Notificación de vigilancia. |
| 6010 | `NOTIF_ALERTA` | Notificación de alerta. |
| 6011 | `NOTIF_CRITICO` | Notificación crítica. |
| 6020 | `NOTIF_DERIVA` | Notificación por deriva lenta. |

### 7xxx · Chat (`/preguntar`)

| Código | Nombre | Significado |
|---|---|---|
| 7001 | `RESPUESTA_OK` | Respuesta del agente generada. |

### 9xxx · Errores

| Código | Nombre | Significado |
|---|---|---|
| 9001 | `TRIPULANTE_NO_ENCONTRADO` | El tripulante no existe. |
| 9002 | `VARIABLE_DESCONOCIDA` | La medida solicitada no existe. |
| 9003 | `LLM_NO_DISPONIBLE` | LM Studio no responde. |

## Ejemplos

`GET /tripulantes/astro_3/aptitud`
```json
{
  "usuario": "astro_3", "apto": true, "codigo": 1002, "estado": "APTO_CON_SEGUIMIENTO", "nivel": "VIGILAR",
  "motivos": [],
  "observaciones": [{"codigo": 5005, "nombre": "DERIVA_LENTA_HALLAZGO", "variable": "pulso",
                     "mensaje": "pulso: deriva lenta ascendente de 9.1 bpm (respecto a línea base; umbral 8.0)"}],
  "recomendaciones": ["Apto con seguimiento: repetir medición en los próximos minutos."],
  "derivadas": {"presion_pulso": 48.6, "presion_media": 83.6, "indice_choque": 0.5}
}
```
No apto: `"apto": false, "codigo": 1010` (RIESGO) o `1011` (CRITICO) y `motivos` con al menos un evento.

Error: `{"detail": {"codigo": 9001, "nombre": "TRIPULANTE_NO_ENCONTRADO", "mensaje": "..."}}`

## Reglas de decisión (resumen)

- **No apto (1011)**: alguna medida en nivel crítico (5001).
- **No apto (1010)**: alerta clínica sostenida 3 lecturas (5002) aunque el modelo la vea normal; alerta clínica + fuera de su patrón (5003/5015); deriva lenta con el valor ya fuera de rango (5005 como motivo); patrón respiratorio (5004).
- **Apto con seguimiento (1002)**: solo observaciones (5006, 5007-5014, deriva con valor aún normal).
- **Saludable (1001)**: sin motivos ni observaciones.
- **Deriva lenta (4110)**: el promedio de las últimas 6 lecturas se aleja de la línea base o de hace ~6 h más que `max(umbral por variable, 2σ de su línea base)` (pulso 8 bpm, SpO2 2 %, sistólica 10 y diastólica 6 mmHg).
- **Línea base no confiable (5006)**: la línea base de esa persona ya estaba en alerta clínica; manda el criterio clínico.
