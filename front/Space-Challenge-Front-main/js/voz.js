/* ORBITAL · voz: lee en voz alta lo que devuelve el backend (respuestas del chat, notificaciones, aptitud).
   Port en JS plano de docs/front/voz.ts del backend (docs/FRONT.md §10). Web Speech API, sin internet si hay voz local.
   Expone window.OrbitalVoz = { voz, lectorStream, textoNotificacion, textoAptitud, limpiar }. */
(function () {
  'use strict';
  var CLAVE = 'voz.activa';
  var disponible = typeof window !== 'undefined' && 'speechSynthesis' in window;
  var activa = true;
  try { activa = localStorage.getItem(CLAVE) !== '0'; } catch (e) { }

  var vozElegida = null;
  var vivos = new Set();   // Chrome puede liberar el utterance antes de terminar: se guarda la referencia.

  function elegirVoz() {
    var es = speechSynthesis.getVoices().filter(function (v) { return v.lang.toLowerCase().indexOf('es') === 0; });
    var puntos = function (v) { return (v.localService ? 4 : 0) + (/es[-_](mx|us|419)/i.test(v.lang) ? 2 : 0) + (v.default ? 1 : 0); };
    vozElegida = es.sort(function (a, b) { return puntos(b) - puntos(a); })[0] || null;
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
    hablar: function (texto, opts) {
      opts = opts || {};
      if (!disponible || !activa) return;
      var limpio = limpiar(texto); if (!limpio) return;
      if (opts.interrumpir) speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(limpio);
      u.lang = vozElegida ? vozElegida.lang : 'es-MX';
      if (vozElegida) u.voice = vozElegida;
      u.rate = opts.velocidad || 1;
      vivos.add(u);
      u.onend = u.onerror = function () { vivos.delete(u); if (opts.alTerminar) opts.alTerminar(); };
      speechSynthesis.speak(u);
    },
    callar: function () { if (!disponible) return; speechSynthesis.cancel(); vivos.clear(); }
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

  var SEVERIDAD = { VIGILAR: 'Aviso', ALERTA: 'Alerta', CRITICO: 'Alerta crítica' };
  function textoNotificacion(n, nombre) { return (SEVERIDAD[n.severidad] || 'Aviso') + ', ' + (nombre || n.usuario) + '. ' + n.mensaje + '.'; }
  function textoAptitud(a, nombre) {
    var base = (nombre || a.usuario) + ': ' + (a.apto ? 'apto' : 'no apto') + '. Estado: ' + String(a.estado).replace(/_/g, ' ').toLowerCase() + '.';
    return a.recomendaciones && a.recomendaciones.length ? base + ' Recomendaciones: ' + a.recomendaciones.join('. ') + '.' : base;
  }

  window.OrbitalVoz = { voz: voz, lectorStream: lectorStream, textoNotificacion: textoNotificacion, textoAptitud: textoAptitud, limpiar: limpiar };
})();
