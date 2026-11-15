/* ORBITAL · voz: lee en voz alta lo que devuelve el backend (respuestas del chat, notificaciones, aptitud).
   Port en JS plano de docs/front/voz.ts del backend (docs/FRONT.md §10). Web Speech API, sin internet si hay voz local.
   Expone window.OrbitalVoz = { voz, lectorStream, textoNotificacion, textoAptitud, limpiar }. */
(function () {
  'use strict';
  var CLAVE = 'voz.activa';
  var disponible = typeof window !== 'undefined' && 'speechSynthesis' in window;
  var activa = true;
  try { activa = localStorage.getItem(CLAVE) !== '0'; } catch (e) { }

  var vozElegida = null, vozLocal = null;
  var vivos = new Set();   // Chrome puede liberar el utterance antes de terminar: se guarda la referencia.
  var oyentes = [];        // fn(hablando, texto): para animar la esfera / subtítulos y el botón de silencio.
  function avisar(hablando, texto) { oyentes.forEach(function (fn) { try { fn(hablando, texto); } catch (e) { } }); }

  /* Voz cálida: se prefieren las voces neuronales/"Natural" (Edge, Windows 11, macOS Premium) y, entre las
     clásicas, voces femeninas suaves conocidas. eSpeak (la voz local por defecto en Linux) suena robótica y va al final.
     Si la voz elegida es de red y falla (sin internet), se reintenta con la mejor voz local (vozLocal). */
  var CALIDAS = /dalia|paulina|sabina|m[oó]nica|elvira|ximena|renata|marisol|helena|laura|elena|google espa/i;
  function puntos(v) {
    var n = v.name || '';
    return (/natural|neural|premium|enhanced|mejorad/i.test(n) ? 20 : 0) + (CALIDAS.test(n) ? 8 : 0) +
      (/es[-_](mx|us|419)/i.test(v.lang) ? 3 : 0) + (v.localService ? 1 : 0) - (/espeak|robot/i.test(n) ? 15 : 0);
  }
  function elegirVoz() {
    var es = speechSynthesis.getVoices().filter(function (v) { return v.lang.toLowerCase().indexOf('es') === 0; })
      .sort(function (a, b) { return puntos(b) - puntos(a); });
    vozElegida = es[0] || null;
    vozLocal = es.filter(function (v) { return v.localService; })[0] || null;
  }
  if (disponible) { elegirVoz(); speechSynthesis.addEventListener('voiceschanged', elegirVoz); }

  var NOMBRES = {
    spo2: 'saturación de oxígeno', presion_sistolica: 'presión sistólica', presion_diastolica: 'presión diastólica',
    sueno_latencia: 'latencia de sueño', sueno_duracion: 'duración del sueño', sueno_eficiencia: 'eficiencia del sueño',
    mmhg: 'milímetros de mercurio', bpm: 'latidos por minuto'
  };

  function limpiar(texto) {
    return String(texto || '')
      .replace(/\[[^\]]*\]/g, '')
      .replace(/[*#`>|]/g, '')
      .replace(/\b(spo2|presion_sistolica|presion_diastolica|sueno_latencia|sueno_duracion|sueno_eficiencia|mmHg|bpm)\b/gi, function (m) { return NOMBRES[m.toLowerCase()] || m; })
      .replace(/(\d)\.(\d)/g, '$1,$2')
      .replace(/\s*=\s*/g, ' ')
      .replace(/_/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  var voz = {
    disponible: disponible,
    get activa() { return activa; },
    activar: function (valor) {
      activa = valor;
      try { localStorage.setItem(CLAVE, valor ? '1' : '0'); } catch (e) { }
      if (!valor) voz.callar();
    },
    hayVozEnEspanol: function () { return vozElegida !== null; },
    get hablando() { return vivos.size > 0; },
    // Suscribe fn(hablando, texto). Devuelve la función para desuscribirse.
    alCambiar: function (fn) { oyentes.push(fn); return function () { oyentes = oyentes.filter(function (f) { return f !== fn; }); }; },
    hablar: function (texto, opts) {
      opts = opts || {};
      if (!disponible || !activa) return;
      var limpio = limpiar(texto); if (!limpio) return;
      if (opts.interrumpir) voz.callar();
      decir(limpio, opts, vozElegida);
    },
    callar: function () { if (!disponible) return; vivos.clear(); speechSynthesis.cancel(); avisar(false, ''); }
  };

  function decir(limpio, opts, v) {
    var u = new SpeechSynthesisUtterance(limpio);
    u.lang = v ? v.lang : 'es-MX';
    if (v) u.voice = v;
    u.rate = opts.velocidad || 0.95;   // un poco más pausado y grave suena más cercano
    u.pitch = 1.05;
    vivos.add(u);
    u.onstart = function () { if (vivos.has(u)) avisar(true, limpio); };
    u.onend = function () { vivos.delete(u); if (!vivos.size) avisar(false, ''); if (opts.alTerminar) opts.alTerminar(); };
    u.onerror = function (e) {
      var cancelado = !vivos.has(u) || (e && (e.error === 'canceled' || e.error === 'interrupted'));
      vivos.delete(u);
      // Voz de red sin conexión: se repite con la voz local para no perder el aviso.
      if (!cancelado && activa && v && !v.localService && vozLocal) return decir(limpio, opts, vozLocal);
      if (!vivos.size) avisar(false, '');
      if (opts.alTerminar) opts.alTerminar();
    };
    speechSynthesis.speak(u);
  }

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

  var SEVERIDAD = { VIGILAR: 'Aviso', ALERTA: 'Alerta', CRITICO: 'Alerta crítica' };
  function textoNotificacion(n, nombre) { return (SEVERIDAD[n.severidad] || 'Aviso') + ', ' + (nombre || n.usuario) + '. ' + n.mensaje + '.'; }
  function textoAptitud(a, nombre) {
    var base = (nombre || a.usuario) + ': ' + (a.apto ? 'apto' : 'no apto') + '. Estado: ' + String(a.estado).replace(/_/g, ' ').toLowerCase() + '.';
    return a.recomendaciones && a.recomendaciones.length ? base + ' Recomendaciones: ' + a.recomendaciones.join('. ') + '.' : base;
  }

  window.OrbitalVoz = { voz: voz, lectorStream: lectorStream, textoNotificacion: textoNotificacion, textoAptitud: textoAptitud, limpiar: limpiar };
})();
