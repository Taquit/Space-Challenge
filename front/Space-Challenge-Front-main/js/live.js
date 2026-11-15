/* ORBITAL · capa "en vivo": toma los datos reales del backend (OrbitalAPI) y los deja en la MISMA
   forma que usa el prototipo (series, sueño, cognición, banda personal), para no reescribir las vistas.
   Puro: no toca React ni el DOM. El cableado (setState, SSE) vive en index.html.
   Si el backend no responde, el prototipo sigue en modo demostración con sus datos sintéticos.
   Los estados (colores, ÓPTIMO/VIGILAR/ALERTA/CRÍTICO, apto/no apto, 8xxx) salen de los CÓDIGOS del backend
   (docs/CODIGOS.md); el cliente no reclasifica valores cuando hay respuesta del backend.
   Expone window.OrbitalLive. */
(function () {
  'use strict';
  var A = window.OrbitalAPI;

  // Identidad de diseño -> id del backend. Carlos no está en el backend (tarjeta "sin sensor").
  var BACKEND_ID = { katya: 'astro_1', jose: 'astro_2', rodolfo: 'astro_3' };
  var VITALES = ['pulso', 'spo2', 'presion_sistolica', 'presion_diastolica'];
  // Métrica de sueño del front -> variable del backend
  var SUENO = { dur: 'sueno_duracion', eff: 'sueno_eficiencia', lat: 'sueno_latencia' };
  // Prueba del front -> métrica principal que evalúa el backend (cognitivo.evaluacion.metricas)
  var COG_METRICA = { pvt: 'cog_pvt_rt', dsst: 'cog_dsst_throughput', matrix: 'cog_matrix_correctas' };
  // Nivel textual del backend -> código 8xxx
  var NIVEL_COG = { SIN_LINEA_BASE: 8000, NORMAL: 8001, VIGILAR: 8002, ALERTA: 8010 };

  function mean(a) { return a.reduce(function (x, y) { return x + y; }, 0) / a.length; }
  function sd(a) { if (a.length < 2) return 0; var m = mean(a); return Math.sqrt(mean(a.map(function (x) { return (x - m) * (x - m); }))); }

  // Severidad visual (-1 sin datos, 0 óptimo, 1 vigilar, 2 alerta, 3 crítico) a partir de un código xyyy del backend.
  function sevDeCodigo(c) {
    if (c == null) return -1;
    var r = c % 1000;
    return r === 0 ? -1 : r === 1 ? 0 : r === 2 ? 1 : r === 10 ? 2 : r === 11 ? 3 : -1;
  }

  // Serie {var:[valores]} a partir del historial del backend ([{timestamp, valores}]).
  function seriesDeHistorial(historial) {
    var out = {}; VITALES.forEach(function (k) { out[k] = []; });
    (historial || []).forEach(function (h) { VITALES.forEach(function (k) { if (h.valores && h.valores[k] != null) out[k].push(h.valores[k]); }); });
    return out;
  }

  // Banda personal [lo, hi, base, sd]: usa el rango esperado del backend si existe; si no (modelo sin entrenar), lo calcula de la serie.
  function bandaDe(serie, resumenMedida) {
    var vals = serie.filter(function (v) { return v != null; });
    var base = vals.length ? mean(vals) : 0, s = Math.max(sd(vals), 0.5);
    if (resumenMedida && resumenMedida.esperado_personal && resumenMedida.esperado_personal.lower != null) {
      var ep = resumenMedida.esperado_personal;
      var b = resumenMedida.linea_base != null ? resumenMedida.linea_base : (ep.valor != null ? ep.valor : base);
      return [ep.lower, ep.upper, b, Math.max((ep.upper - ep.lower) / 4, 0.5)];
    }
    if (resumenMedida && resumenMedida.linea_base != null) base = resumenMedida.linea_base;
    return [base - 2 * s, base + 2 * s, base, s];
  }

  // Noches de sueño del backend -> {dur:[],eff:[],lat:[],meds:[],fechas:[]} (en orden, más antigua primero).
  function sleepDeNoches(noches) {
    if (!noches || !noches.length) return null;
    var dur = [], eff = [], lat = [], meds = [], fechas = [];
    noches.forEach(function (n) {
      var v = n.valores || {};
      if (v.sueno_duracion != null) dur.push(v.sueno_duracion);
      if (v.sueno_eficiencia != null) eff.push(v.sueno_eficiencia);
      if (v.sueno_latencia != null) lat.push(v.sueno_latencia);
      meds.push(n.medicacion || null); fechas.push(n.timestamp);
    });
    if (!dur.length) return null;
    return { dur: dur, eff: eff, lat: lat, meds: meds, fechas: fechas };
  }

  /* Historial cognitivo del backend (GET /cognitivo) -> arrays por prueba para la vista, más el nivel OFICIAL
     de cada sesión (evaluacion.metricas[...].nivel). Las sesiones de familiarización se omiten: el backend las
     descarta de la línea base, así B1–B3 de la vista coinciden con las 3 sesiones de línea base del backend. */
  function cogDeSesiones(sesiones) {
    var out = { pvt: [], dsst: [], matrix: [], niveles: { pvt: [], dsst: [], matrix: [] }, total: 0 };
    (sesiones || []).forEach(function (s) {
      out.total++;
      if (s.familiarizacion) return;
      var p = s.pruebas || {}, met = (s.evaluacion && s.evaluacion.metricas) || {};
      var push = function (t, v) { out[t].push(v); out.niveles[t].push(met[COG_METRICA[t]] ? met[COG_METRICA[t]].nivel : null); };
      if (p.pvt && p.pvt.rt_mediana_ms != null) push('pvt', p.pvt.rt_mediana_ms);
      if (p.dsst && p.dsst.correctas != null) push('dsst', p.dsst.correctas);
      if (p.matrix && p.matrix.correctas != null) push('matrix', p.matrix.correctas);
    });
    return out;
  }

  /* /resumen -> forma de MockAPI.resumen (una entrada por signo vital) con los códigos del backend.
     `series` = cr.series (valores en vivo del stream) para mostrar el valor más reciente sin esperar al siguiente /resumen. */
  function resDeResumen(resumen, series, band) {
    var med = resumen && resumen.medidas; if (!med) return null;
    var out = {}, n = 0;
    VITALES.forEach(function (k) {
      var m = med[k]; if (!m) return;
      var s = (series && series[k]) || [], v = s.length ? s[s.length - 1] : m.actual;
      var ep = m.esperado_personal, b = band && band[k];
      var lo = ep && ep.lower != null ? ep.lower : (b ? b[0] : m.minimo), hi = ep && ep.upper != null ? ep.upper : (b ? b[1] : m.maximo);
      var clin = m.codigo_nivel_clinico, modelo = m.codigo_estado_modelo, deriva = m.deriva && m.deriva.detectada;
      var sev = Math.max(sevDeCodigo(clin), sevDeCodigo(modelo), deriva ? 1 : 0, 0);
      var dir = deriva && m.deriva.sentido ? (/desc/.test(m.deriva.sentido) ? 'por debajo' : 'por encima') : (v < lo ? 'por debajo' : 'por encima');
      out[k] = { valor: v, rango_esperado: [lo, hi], linea_base: m.linea_base, codigo_clinico: clin, codigo_modelo: modelo,
        tendencia: m.codigo_tendencia, sev: sev, dir: dir, deriva: !!deriva,
        interpretacion: m.nivel_clinico && m.nivel_clinico !== 'NORMAL' ? m.interpretacion_clinica : null };
      n++;
    });
    return n ? out : null;
  }

  // Severidad clínica por noche (última) de cada métrica de sueño según /resumen. {dur, eff, lat} o null.
  function sleepSevDeResumen(resumen) {
    var med = resumen && resumen.medidas; if (!med) return null;
    var out = {}, n = 0;
    Object.keys(SUENO).forEach(function (k) { var m = med[SUENO[k]]; if (m) { out[k] = Math.max(0, sevDeCodigo(m.codigo_nivel_clinico), m.deriva && m.deriva.detectada ? 1 : 0); n++; } });
    return n ? out : null;
  }

  // Fecha ISO 8601 con zona local, p. ej. "2026-11-15T09:30:00-06:00" (formato que pide POST /cognitivo).
  function isoLocal(d) {
    d = d || new Date();
    var p = function (n) { return String(Math.floor(Math.abs(n))).padStart(2, '0'); }, off = -d.getTimezoneOffset();
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()) +
      (off >= 0 ? '+' : '-') + p(off / 60) + ':' + p(off % 60);
  }

  async function intento(fn) { try { return await fn(); } catch (e) { return null; } }

  window.OrbitalLive = {
    BACKEND_ID: BACKEND_ID,
    VITALES: VITALES,
    NIVEL_COG: NIVEL_COG,
    sevDeCodigo: sevDeCodigo,
    resDeResumen: resDeResumen,
    sleepSevDeResumen: sleepSevDeResumen,
    cogDeSesiones: cogDeSesiones,
    sleepDeNoches: sleepDeNoches,
    bandaDe: bandaDe,

    // ¿Está el backend disponible? Devuelve el objeto /salud o null.
    detectar: function () { return A.ping(2500); },

    /* Inferencias del backend para un tripulante: {resumen, aptitud, cogHist, cogResumen}. Cada parte es null si falla. */
    cargarDetalle: async function (bid) {
      var r = await Promise.all([intento(function () { return A.resumen(bid); }), intento(function () { return A.aptitud(bid); }),
        intento(function () { return A.cognitivo(bid); }), intento(function () { return A.cognitivoResumen(bid); })]);
      return { resumen: r[0], aptitud: r[1], cogHist: r[2], cogResumen: r[3] };
    },

    /* Enriquece el arreglo de tripulantes de diseño con datos reales del backend.
       Mantiene identidad (name, role, task, order, seed, temp) y reemplaza series/band/sleep/cog por lo real.
       Para los que no están en el backend (Carlos) conserva su estado sintético (noData o demo).
       Devuelve {crew, detalle} (detalle por id de diseño) o lanza si falla la carga de la lista. */
    cargarCrew: async function (designCrew) {
      var lista = await A.tripulantes();                 // [{id, variables, lecturas_disponibles, noches_disponibles}]
      var porId = {}; lista.forEach(function (t) { porId[t.id] = t; });
      var detalle = {};

      var crew = await Promise.all(designCrew.map(async function (base) {
        var bid = BACKEND_ID[base.id];
        if (!bid || !porId[bid]) return Object.assign({}, base);   // Carlos u otros: queda como está (demo/sin sensor)

        var salud = await A.saludTripulante(bid, 200);              // historial + sueño actuales
        var serie = seriesDeHistorial(salud.historial);
        var sleep = sleepDeNoches(salud.sueno);
        var det = await this_.cargarDetalle(bid); detalle[base.id] = det;

        var med = (det.resumen && det.resumen.medidas) || {}, band = {};
        VITALES.forEach(function (k) { if (serie[k] && serie[k].length) band[k] = bandaDe(serie[k], med[k]); });
        var cog = det.cogHist ? cogDeSesiones(det.cogHist.sesiones) : { pvt: [], dsst: [], matrix: [], niveles: { pvt: [], dsst: [], matrix: [] }, total: 0 };

        // "days" (histórico largo) no existe en el backend (solo 1 día): se deja el sintético del diseño, etiquetado como demo en la UI.
        return Object.assign({}, base, {
          backendId: bid, live: true, noData: false,
          series: Object.assign({}, base.series || {}, serie),
          band: Object.assign({}, base.band || {}, band),
          sleep: sleep,                                   // null si el tripulante no tiene sueño (astro_3 / Rodolfo)
          cog: cog,
          vars: porId[bid].variables, nights: porId[bid].noches_disponibles
        });
      }));

      return { crew: crew, detalle: detalle };
    },

    /* Payload de una sesión cognitiva (PVT) para POST /tripulantes/{id}/cognitivo (FRONT.md §9).
       `primera` = el tripulante no tiene sesiones aún: se marca como familiarización (se descarta de la línea base). */
    sesionPVT: function (trials, early, primera) {
      var ordenados = trials.slice().sort(function (a, b) { return a - b; });
      var media = ordenados.reduce(function (x, y) { return x + y; }, 0) / ordenados.length;
      var mediana = ordenados.length % 2 ? ordenados[(ordenados.length - 1) / 2] : (ordenados[ordenados.length / 2 - 1] + ordenados[ordenados.length / 2]) / 2;
      var lapsos = trials.filter(function (t) { return t > 500; }).length;
      return {
        fecha: isoLocal(),
        forma: 'A', semilla: Math.floor(Math.random() * 100000), familiarizacion: !!primera,
        pruebas: { pvt: { rt_media_ms: Math.round(media * 10) / 10, rt_mediana_ms: Math.round(mediana * 10) / 10, lapsos: lapsos, falsos_inicios: early || 0, n_estimulos: trials.length } },
        contexto: { comentario: '' }
      };
    }
  };
  var this_ = window.OrbitalLive;
})();
