/* ORBITAL · voz: lee en voz alta lo que devuelve el backend (respuestas del chat, notificaciones, aptitud).
   Port en JS plano de docs/front/voz.ts del backend (docs/FRONT.md §10).
   Voz principal: Piper en el backend (POST /voz → WAV), cálida y sin internet; idioma según OrbitalI18n (es / en).
   Respaldo: Web Speech API del navegador si el backend o la voz de Piper no están disponibles (no se pierde ningún aviso).
   Expone window.OrbitalVoz = { voz, lectorStream, textoNotificacion, textoAptitud, limpiar }. */
(function () {
  'use strict';
  var CLAVE = 'voz.activa';
  var IDIOMA = (window.OrbitalI18n && window.OrbitalI18n.idioma) === 'en' ? 'en' : 'es';
  var web = typeof window !== 'undefined' && 'speechSynthesis' in window;
  var disponible = web || typeof Audio !== 'undefined';
  var activa = true;
  try { activa = localStorage.getItem(CLAVE) !== '0'; } catch (e) { }

  var oyentes = [];        // fn(hablando, texto): para animar la esfera / subtítulos y el botón de silencio.
  function avisar(hablando, texto) { oyentes.forEach(function (fn) { try { fn(hablando, texto); } catch (e) { } }); }

  /* ---------- Piper (backend) ---------- */
  var piperFueraHasta = 0;   // si /voz falla, se usa la voz del navegador un rato antes de reintentar
  function api() { return (window.ORBITAL_API_BASE || '').replace(/\/$/, ''); }
  function piperUsable() { return !window.ORBITAL_FORCE_DEMO && typeof fetch !== 'undefined' && Date.now() > piperFueraHasta; }
  function pedirAudio(texto) {
    return fetch(api() + '/voz', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ texto: texto, idioma: IDIOMA }) })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.blob(); })
      .then(function (b) { return URL.createObjectURL(b); })
      .catch(function () { piperFueraHasta = Date.now() + 60000; return null; });
  }

  /* ---------- Voz del navegador (respaldo) ---------- */
  var vozElegida = null, vozLocal = null;
  /* Voz cálida: se prefieren las voces neuronales/"Natural" (Edge, Windows 11, macOS Premium) y, entre las
     clásicas, voces femeninas suaves conocidas. eSpeak (la voz local por defecto en Linux) suena robótica y va al final. */
  var CALIDAS = IDIOMA === 'en' ? /aria|jenny|samantha|ava|allison|susan|zira|google us/i
    : /dalia|paulina|sabina|m[oó]nica|elvira|ximena|renata|marisol|helena|laura|elena|google espa/i;
  var REGION = IDIOMA === 'en' ? /en[-_]us/i : /es[-_](mx|us|419)/i;
  function puntos(v) {
    var n = v.name || '';
    return (/natural|neural|premium|enhanced|mejorad/i.test(n) ? 20 : 0) + (CALIDAS.test(n) ? 8 : 0) +
      (REGION.test(v.lang) ? 3 : 0) + (v.localService ? 1 : 0) - (/espeak|robot/i.test(n) ? 15 : 0);
  }
  function elegirVoz() {
    var vs = speechSynthesis.getVoices().filter(function (v) { return v.lang.toLowerCase().indexOf(IDIOMA) === 0; })
      .sort(function (a, b) { return puntos(b) - puntos(a); });
    vozElegida = vs[0] || null;
    vozLocal = vs.filter(function (v) { return v.localService; })[0] || null;
  }
  if (web) { elegirVoz(); speechSynthesis.addEventListener('voiceschanged', elegirVoz); }

  /* ---------- Cola de frases ---------- */
  // Cada frase pide su audio a Piper en cuanto entra a la cola (se sintetiza mientras suena la anterior).
  var cola = [], actual = null, audio = null, gen = 0;

  function terminar(item) {
    if (item.hecho) return; item.hecho = true;
    if (item.url) URL.revokeObjectURL(item.url);
    if (item.opts.alTerminar) { try { item.opts.alTerminar(); } catch (e) { } }
  }
  function siguiente() {
    actual = null;
    if (!cola.length) { avisar(false, ''); return; }
    var item = cola.shift(), g = gen; actual = item;
    (item.audio || Promise.resolve(null)).then(function (url) {
      if (g !== gen || item.hecho) return;
      item.url = url;
      if (!url) return decirWeb(item, g);
      audio = new Audio(url);
      audio.onplay = function () { if (g === gen) avisar(true, item.texto); };
      audio.onended = function () { if (g !== gen) return; audio = null; terminar(item); siguiente(); };
      audio.onerror = function () { if (g !== gen) return; audio = null; decirWeb(item, g); };
      audio.play().catch(function () { if (g !== gen) return; audio = null; decirWeb(item, g); });   // autoplay bloqueado, etc.
    });
  }

  function decirWeb(item, g, v) {
    if (!web) { terminar(item); return siguiente(); }
    v = v === undefined ? vozElegida : v;
    var u = new SpeechSynthesisUtterance(item.texto);
    u.lang = v ? v.lang : (IDIOMA === 'en' ? 'en-US' : 'es-MX');
    if (v) u.voice = v;
    u.rate = item.opts.velocidad || 0.95;   // un poco más pausado y grave suena más cercano
    u.pitch = 1.05;
    item.u = u;   // Chrome puede liberar el utterance antes de terminar: se guarda la referencia.
    u.onstart = function () { if (g === gen) avisar(true, item.texto); };
    u.onend = function () { if (g !== gen) return; terminar(item); siguiente(); };
    u.onerror = function (e) {
      if (g !== gen) return;
      var cancelado = e && (e.error === 'canceled' || e.error === 'interrupted');
      // Voz de red sin conexión: se repite con la voz local para no perder el aviso.
      if (!cancelado && v && !v.localService && vozLocal) return decirWeb(item, g, vozLocal);
      terminar(item); siguiente();
    };
    speechSynthesis.speak(u);
  }

  var NOMBRES = IDIOMA === 'en' ? {
    spo2: 'oxygen saturation', presion_sistolica: 'systolic pressure', presion_diastolica: 'diastolic pressure',
    sueno_latencia: 'sleep latency', sueno_duracion: 'sleep duration', sueno_eficiencia: 'sleep efficiency',
    mmhg: 'millimeters of mercury', bpm: 'beats per minute'
  } : {
    spo2: 'saturación de oxígeno', presion_sistolica: 'presión sistólica', presion_diastolica: 'presión diastólica',
    sueno_latencia: 'latencia de sueño', sueno_duracion: 'duración del sueño', sueno_eficiencia: 'eficiencia del sueño',
    mmhg: 'milímetros de mercurio', bpm: 'latidos por minuto'
  };

  function limpiar(texto) {
    var t = String(texto || '')
      .replace(/\[[^\]]*\]/g, '')
      .replace(/[*#`>|]/g, '')
      .replace(/\b(spo2|presion_sistolica|presion_diastolica|sueno_latencia|sueno_duracion|sueno_eficiencia|mmHg|bpm)\b/gi, function (m) { return NOMBRES[m.toLowerCase()] || m; });
    if (IDIOMA === 'es') t = t.replace(/(\d)\.(\d)/g, '$1,$2');   // en español el decimal se lee con coma
    return t.replace(/\s*=\s*/g, ' ').replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
  }

  var voz = {
    disponible: disponible,
    idioma: IDIOMA,
    get activa() { return activa; },
    activar: function (valor) {
      activa = valor;
      try { localStorage.setItem(CLAVE, valor ? '1' : '0'); } catch (e) { }
      if (!valor) voz.callar();
    },
    hayVozEnEspanol: function () { return vozElegida !== null || piperUsable(); },
    get hablando() { return !!actual || cola.length > 0; },
    // Suscribe fn(hablando, texto). Devuelve la función para desuscribirse.
    alCambiar: function (fn) { oyentes.push(fn); return function () { oyentes = oyentes.filter(function (f) { return f !== fn; }); }; },
    hablar: function (texto, opts) {
      opts = opts || {};
      if (!disponible || (!activa && !opts.forzar)) return;   // forzar: alertas críticas, suenan aunque esté silenciado
      var limpio = limpiar(texto); if (!limpio) return;
      if (opts.interrumpir) voz.callar();
      cola.push({ texto: limpio, opts: opts, audio: piperUsable() ? pedirAudio(limpio) : null });
      if (!actual) siguiente();
    },
    callar: function () {
      gen++;
      var pendientes = (actual ? [actual] : []).concat(cola);
      cola = []; actual = null;
      if (audio) { try { audio.pause(); } catch (e) { } audio = null; }
      if (web) speechSynthesis.cancel();
      pendientes.forEach(function (it) {
        if (it.audio && !it.url) it.audio.then(function (u) { if (u) URL.revokeObjectURL(u); });
        terminar(it);
      });
      avisar(false, '');
    }
  };

  // Lee un texto que llega por partes (eventos `token` de /preguntar/stream), oración por oración.
  function lectorStream(opts) {
    var buf = '';
    function corte() {
      var re = /[.!?…]+\s/g, m;
      while ((m = re.exec(buf))) {
        var fin = m.index + m[0].length, previo = buf.slice(0, fin);
        if (previo.lastIndexOf('[') <= previo.lastIndexOf(']')) return fin;
      }
      return -1;
    }
    return {
      agregar: function (token) { buf += token; for (var i; (i = corte()) !== -1;) { voz.hablar(buf.slice(0, i), opts); buf = buf.slice(i); } },
      fin: function () { voz.hablar(buf, opts); buf = ''; },
      cancelar: function () { buf = ''; voz.callar(); }
    };
  }

  var EN = IDIOMA === 'en', I18 = window.OrbitalI18n;
  var SEVERIDAD = EN ? { VIGILAR: 'Notice', ALERTA: 'Alert', CRITICO: 'Critical alert' } : { VIGILAR: 'Aviso', ALERTA: 'Alerta', CRITICO: 'Alerta crítica' };
  function textoNotificacion(n, nombre) {
    var msg = I18 ? I18.evento(n) : n.mensaje;
    return (SEVERIDAD[n.severidad] || SEVERIDAD.VIGILAR) + ', ' + (nombre || n.usuario) + '. ' + msg + '.';
  }
  function textoAptitud(a, nombre) {
    var recs = (a.recomendaciones || []).map(function (r) { return I18 ? I18.backend(r) : r; });
    var estado = String(a.estado);
    estado = (I18 ? I18.backend(estado) : estado).replace(/_/g, ' ').toLowerCase();
    var base = (nombre || a.usuario) + ': ' + (a.apto ? (EN ? 'fit' : 'apto') : (EN ? 'not fit' : 'no apto')) + (EN ? '. Status: ' : '. Estado: ') + estado + '.';
    return recs.length ? base + (EN ? ' Recommendations: ' : ' Recomendaciones: ') + recs.join('. ') + '.' : base;
  }

  window.OrbitalVoz = { voz: voz, lectorStream: lectorStream, textoNotificacion: textoNotificacion, textoAptitud: textoAptitud, limpiar: limpiar };
})();
