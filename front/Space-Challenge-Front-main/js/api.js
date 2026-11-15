/* ORBITAL · cliente del backend real (FastAPI de Space-Challenge).
   Sin dependencias. Todas las llamadas usan API_BASE. Lee docs/API.md y docs/FRONT.md del backend.
   Expone window.OrbitalAPI. */
(function () {
  'use strict';
  var API_BASE = (window.ORBITAL_API_BASE || 'http://localhost:8000').replace(/\/$/, '');

  function url(path) { return API_BASE + path; }

  async function getJSON(path, signal) {
    var res = await fetch(url(path), { signal: signal });
    if (!res.ok) { var t = await res.text().catch(function () { return ''; }); var e = new Error('HTTP ' + res.status + ': ' + t); e.status = res.status; throw e; }
    return res.json();
  }

  async function postJSON(path, body) {
    var res = await fetch(url(path), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    var data = await res.json().catch(function () { return null; });
    if (!res.ok) { var e = new Error('HTTP ' + res.status); e.status = res.status; e.data = data; throw e; }
    return data;
  }

  /* Lector SSE sobre fetch (EventSource no admite POST ni cabeceras). Igual que el helper de FRONT.md.
     onEvent(evento, datos). Devuelve una promesa que resuelve al terminar el stream. */
  async function sse(path, onEvent, opts) {
    opts = opts || {};
    var res = await fetch(url(path), {
      method: opts.body ? 'POST' : 'GET',
      headers: opts.body ? { 'Content-Type': 'application/json' } : undefined,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal
    });
    if (!res.ok) throw new Error('HTTP ' + res.status + ': ' + (await res.text().catch(function () { return ''; })));
    var reader = res.body.getReader(), dec = new TextDecoder(), buf = '';
    for (;;) {
      var r = await reader.read();
      if (r.done) break;
      buf += dec.decode(r.value, { stream: true });
      var bloques = buf.split('\n\n'); buf = bloques.pop();
      for (var i = 0; i < bloques.length; i++) {
        var b = bloques[i];
        var mev = b.match(/^event: (.+)$/m), md = b.match(/^data: ([\s\S]*)$/m);
        if (!mev || !md) continue;               // ignora ": ping" de keep-alive
        var datos; try { datos = JSON.parse(md[1]); } catch (e) { datos = md[1]; }
        onEvent(mev[1], datos);
      }
    }
  }

  window.OrbitalAPI = {
    API_BASE: API_BASE,

    // Estado del servicio. {estado, fragmentos_indexados, llm_disponible, modelo_llm}
    salud: function (signal) { return getJSON('/salud', signal); },

    // Disponibilidad rápida (para decidir modo real vs demostración). No lanza: resuelve con el objeto o null.
    ping: async function (timeoutMs) {
      var ctrl = new AbortController(); var t = setTimeout(function () { ctrl.abort(); }, timeoutMs || 2500);
      try { var s = await getJSON('/salud', ctrl.signal); clearTimeout(t); return s; }
      catch (e) { clearTimeout(t); return null; }
    },

    // Lista de tripulantes: [{id, variables, lecturas_disponibles, noches_disponibles}]
    tripulantes: function (signal) { return getJSON('/tripulantes', signal); },

    // Foto actual + historial + sueño. limite = nº de lecturas/noches recientes.
    saludTripulante: function (id, limite, signal) { return getJSON('/tripulantes/' + id + '/salud?limite=' + (limite || 60), signal); },

    // Resumen por medida (estadísticas, tendencia, rango esperado personal, clínico, derivadas, patrones, cognitivo).
    resumen: function (id, variables, limite, signal) {
      var q = [];
      if (variables && variables.length) q.push('variables=' + encodeURIComponent(variables.join(',')));
      if (limite) q.push('limite=' + limite);
      return getJSON('/tripulantes/' + id + '/resumen' + (q.length ? '?' + q.join('&') : ''), signal);
    },

    // Aptitud: {apto, codigo, estado, nivel, motivos, observaciones, recomendaciones, derivadas, cognitivo?}
    aptitud: function (id, signal) { return getJSON('/tripulantes/' + id + '/aptitud', signal); },

    // Notificaciones (desde un id en adelante).
    notificaciones: function (id, desde, signal) { return getJSON('/tripulantes/' + id + '/notificaciones?desde=' + (desde || 0), signal); },

    // Historial cognitivo: {estado, codigo_nivel, sesiones:[{...,evaluacion}]}
    cognitivo: function (id, signal) { return getJSON('/tripulantes/' + id + '/cognitivo', signal); },

    // Resumen cognitivo: línea base, estado, deriva, observaciones. Orientativo.
    cognitivoResumen: function (id, signal) { return getJSON('/tripulantes/' + id + '/cognitivo/resumen', signal); },

    // Guardar una sesión de pruebas (PVT/DSST/Matrix). 201 → {sesion, estado, codigo_nivel, notificaciones}. 422 → error.data.detail.codigo = 9004.
    guardarCognitivo: function (id, sesion) { return postJSON('/tripulantes/' + id + '/cognitivo', sesion); },

    // Catálogo de códigos (1xxx..9xxx).
    codigos: function (signal) { return getJSON('/tripulantes/codigos', signal); },

    // Reinicia la reproducción del día (para demos). 204.
    reiniciarSimulacion: function () { return fetch(url('/tripulantes/reiniciar-simulacion'), { method: 'POST' }); },

    /* Salud en vivo (SSE). handlers: {onSnapshot, onLectura, onSueno, onNotificacion, onFin}. opts.signal para cancelar. */
    streamSalud: function (id, handlers, opts) {
      handlers = handlers || {}; opts = opts || {};
      return sse('/tripulantes/' + id + '/salud/stream?limite=' + (opts.limite || 60), function (ev, d) {
        if (ev === 'snapshot' && handlers.onSnapshot) handlers.onSnapshot(d);
        else if (ev === 'lectura' && handlers.onLectura) handlers.onLectura(d);
        else if (ev === 'sueno' && handlers.onSueno) handlers.onSueno(d);
        else if (ev === 'notificacion' && handlers.onNotificacion) handlers.onNotificacion(d);
        else if (ev === 'fin' && handlers.onFin) handlers.onFin(d);
      }, { signal: opts.signal });
    },

    /* Chat con Orbi (SSE). body: {pregunta, usuario?, variables?}. handlers: {onFuentes, onToken, onFin, onError}. */
    preguntarStream: function (body, handlers, opts) {
      handlers = handlers || {}; opts = opts || {};
      return sse('/preguntar/stream', function (ev, d) {
        if (ev === 'fuentes' && handlers.onFuentes) handlers.onFuentes(d);
        else if (ev === 'token' && handlers.onToken) handlers.onToken(d);
        else if (ev === 'fin' && handlers.onFin) handlers.onFin(d);
        else if (ev === 'error' && handlers.onError) handlers.onError(d);
      }, { body: body, signal: opts.signal });
    }
  };
})();
