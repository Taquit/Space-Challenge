# Umbrales configurables

Todos los umbrales del sistema de salud están en **`umbrales.env`** (raíz del proyecto). Para cambiar un criterio **no se toca código**: edita el valor y **reinicia el backend** (`python -m src.api.main`).

- Formato `CLAVE=valor`; `#` inicia un comentario.
- Una variable de entorno con el mismo nombre tiene prioridad sobre el archivo (útil para pruebas): `SPO2_ALERTA_MIN=94 python -m src.api.main`.
- Para usar otro archivo: `UMBRALES_ENV=otro.env` (ruta relativa a la raíz).
- Si falta una clave se usa el valor por defecto de `src/salud/umbrales.py` (`DEFAULTS`). Una clave desconocida o un valor no numérico detiene el arranque con un error claro.
- Cambiar los umbrales del **modelo** (`MODELO_Z_*`) afecta la clasificación al volver a ejecutar `python -m src.series.analizar`.

| Grupo | Claves | Para qué |
|---|---|---|
| Límites clínicos | `PULSO_*`, `SPO2_*`, `SISTOLICA_*`, `DIASTOLICA_*` (`_VIGILAR`, `_ALERTA`, `_CRITICO`, con `_MIN`/`_MAX`) | Nivel clínico de cada medida (2xxx). Máximos: "≥" (pulso: ">"); mínimos: "<" |
| Derivadas | `INDICE_CHOQUE_MAX`, `PRESION_PULSO_MIN/MAX` | Hallazgos 5008 y 5009 |
| Persistencia / base | `PERSISTENCIA_LECTURAS`, `BASELINE_LECTURAS` | Alerta sostenida (5002) y línea base personal |
| Deriva lenta | `DERIVA_UMBRAL_<VARIABLE>`, `DERIVA_SIGMAS`, `DERIVA_VENTANA_LECTURAS`, `DERIVA_PROMEDIO_LECTURAS`, `DERIVA_REARME_LECTURAS` | Detección (4110) y re-aviso |
| Tendencia | `TENDENCIA_UMBRAL` | Estable / ascendente / descendente |
| Modelo personal | `MODELO_Z_ADVERTENCIA`, `MODELO_Z_ANOMALIA`, `MODELO_Z_ANOMALIA_ISO` | Z-score para 3002 y 3010 |
| Patrones | `PATRON_SPO2_MAX`, `PATRON_MIN_VARIABLES` | Patrón respiratorio (5004) y múltiples desviaciones (5011) |

Los valores por defecto y su explicación están en [`INFERENCIAS.md`](INFERENCIAS.md); el comentario de cada línea de `umbrales.env` indica su unidad.

> Los límites son orientativos (adulto en reposo) y deben ser validados por personal médico.
