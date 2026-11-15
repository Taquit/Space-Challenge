# Pruebas cognitivas: qué se pregunta y para qué sirve cada una

Guía de las tres pruebas del módulo cognitivo (plan en [`COGNITIVO.md`](COGNITIVO.md), contrato del front en [`FRONT.md`](FRONT.md) §9). Cada sesión dura 5 a 7 min.

> Orientativo, **no es diagnóstico médico**. Los resultados se comparan solo contra la línea base de la propia persona.

## Resumen

| Prueba | Qué se le pide a la persona | Qué función mide | Duración | Métrica que se evalúa | Empeora si |
|---|---|---|---|---|---|
| **PVT** | Pulsar al ver el estímulo | Atención sostenida y alerta | ~3 min (1 a 2 si se reduce) | `rt_media_ms`, `lapsos` | **sube** |
| **DSST** | Elegir el número que corresponde a cada símbolo | Velocidad de procesamiento | 90 s | `throughput` | **baja** |
| **Matrix Reasoning** | Elegir la pieza que completa una matriz | Razonamiento abstracto | hasta 12 ítems | `correctas` | **baja** |

Son las tres pruebas que más cambiaron tras una noche sin dormir en Basner et al. 2015 (PVT d=1.00, DSST d=0.68, Matrix d=0.65), por eso son el conjunto mínimo.

## 1. PVT (Psychomotor Vigilance Test)

**La tarea.** Aparece un estímulo tras un intervalo aleatorio de 2 a 10 s. La persona responde lo más rápido posible con un clic o una tecla. No hay respuestas "correctas": solo importa la rapidez.

**Para qué sirve.** Detecta somnolencia y fallos de atención. Es la prueba más sensible a la falta de sueño y a la fatiga, y casi no depende de la educación ni del idioma.

**Qué se guarda.**
- `rt_media_ms` y `rt_mediana_ms`: tiempo de reacción. La media sube con la fatiga; la mediana es más robusta a un solo despiste.
- `lapsos`: respuestas de más de 500 ms (`COG_PVT_LAPSO_MS`). Es la medida clásica de "microdormidas" o distracciones.
- `falsos_inicios`: respuestas antes del estímulo. Se guardan, pero no se evalúan; indican impulsividad o ansiedad por responder.
- `n_estimulos`: cuántos estímulos hubo.

**Cómo se interpreta.** Un `rt_media_ms` o unos `lapsos` más altos que su línea base empujan el estado hacia VIGILAR o ALERTA.

## 2. DSST (Digit Symbol Substitution Test)

**La tarea.** Hay una clave de 9 pares dígito-símbolo en pantalla. Aparece un símbolo y la persona elige el número que le corresponde, tantas veces como pueda en 90 s. La clave se reasigna al azar en cada sesión (la `semilla` queda guardada en la sesión) para que no se memorice.

**Para qué sirve.** Mide la velocidad de procesamiento: atención, memoria de trabajo y coordinación visomotora a la vez. Es sensible a la fatiga y al estrés.

**Qué se guarda.**
- `correctas` e `intentos`, y `precision` = correctas / intentos.
- `throughput` = correctas por segundo. Es la métrica que se evalúa: premia ir rápido sin equivocarse, como en WinSCAT.
- `rt_media_ms`: tiempo medio por respuesta.

**Cómo se interpreta.** Un `throughput` más bajo que su línea base indica que procesa más lento. La precisión se conserva como dato, pero no decide el nivel.

## 3. Matrix Reasoning

**La tarea.** Se muestra una matriz de 3×3 con una celda vacía y varias opciones. La persona elige la pieza que completa el patrón. Son 12 ítems y la prueba se detiene tras 3 errores seguidos. Los ítems se generan con reglas (progresión de forma, color o cantidad) a partir de una semilla, lo que permite formas alternativas.

**Para qué sirve.** Mide razonamiento abstracto y resolución de problemas nuevos. Es la prueba más "mental" de las tres y complementa a las otras dos, que miden velocidad.

**Qué se guarda.**
- `correctas` (métrica que se evalúa), `intentos` y `precision`.
- `tiempo_total_s` y `throughput` = correctas por segundo.

**Cómo se interpreta.** Menos `correctas` que su línea base empuja el estado hacia VIGILAR o ALERTA. Como el conteo es pequeño (0 a 12), la desviación tiene un piso mínimo de 1 (`COG_SD_MIN_ABS_CONTEO`) para que un error de más no dispare el nivel.

## Cómo se combinan los resultados

1. **Familiarización.** La primera sesión se descarta de la línea base porque el efecto de práctica es mayor al principio.
2. **Línea base.** Las siguientes 3 sesiones fijan lo habitual de esa persona. Hasta tenerlas el estado es `SIN_LINEA_BASE` (8000).
3. **Nivel.** Cada métrica da un z de deterioro (positivo = peor que su base): menos de 1.5 es NORMAL (8001), de 1.5 a 2 VIGILAR (8002), 2 o más ALERTA (8010). El nivel de la sesión es el de su peor métrica.
4. **Alerta sostenida.** Dos sesiones seguidas en ALERTA generan una notificación (6010). Una ALERTA aislada solo sugiere repetir la sesión.
5. **Deriva.** Un empeoramiento lento a lo largo de varias sesiones genera 4110 y una notificación (6020).
6. **Cruces.** Si el nivel es VIGILAR o peor, se revisa si coincide con sueño deficiente (5019) o con signos vitales desviados (5020).

## Qué no hacen

- **No declaran "no apto".** Solo añaden observaciones y llevan a "Apto con seguimiento" (1002).
- **No diagnostican.** Una sesión mala suele deberse a fatiga, distracción o poco esfuerzo; por eso la recomendación es repetir la sesión y descartar esas causas.
- **No son las pruebas originales** (Penn CNB, ANAM, WinSCAT). Son versiones propias con el mismo paradigma y estímulos generados por algoritmo; sus propiedades psicométricas no están validadas.
- **Dependen del equipo.** El tiempo de reacción se mide en el navegador, así que conviene usar el mismo dispositivo en todas las sesiones.
