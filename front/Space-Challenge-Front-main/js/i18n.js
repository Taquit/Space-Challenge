/* ORBITAL · idioma de la interfaz y de la voz (español / inglés).
   - El idioma se guarda en localStorage ('orbital.idioma') y también acepta ?idioma=en en la URL.
   - En inglés, ANTES de que support.js arranque (DOMContentLoaded), se traducen los textos de la plantilla <x-dc>
     y los fragmentos del <script data-dc-script> con el diccionario de js/i18n-en.js. Por eso cambiar de idioma recarga.
   - Los mensajes que llegan del backend (avisos, motivos, recomendaciones) pasan por OrbitalI18n.evento()/backend():
     glosario + respaldo por código de evento, para que nunca se muestre ni se lea texto en español en modo inglés.
   Expone window.OrbitalI18n = { idioma, cambiar, alternar, backend, evento }. Debe cargarse ANTES de js/support.js. */
(function () {
  'use strict';
  var CLAVE = 'orbital.idioma';
  var idioma = 'es';
  try { var g = localStorage.getItem(CLAVE); if (g === 'en' || g === 'es') idioma = g; } catch (e) { }
  try { var q = new URLSearchParams(location.search).get('idioma'); if (q === 'en' || q === 'es') idioma = q; } catch (e) { }
  document.documentElement.lang = idioma;

  function D() { return window.ORBITAL_I18N_EN || {}; }
  function reemplazar(t, pares) {
    for (var i = 0; i < pares.length; i++) if (t.indexOf(pares[i][0]) !== -1) t = t.split(pares[i][0]).join(pares[i][1]);
    return t;
  }

  // Traduce la plantilla y el código del componente antes del arranque.
  function aplicar() {
    if (idioma !== 'en') return;
    var d = D(), dc = document.querySelector('x-dc');
    if (!dc || !d.plantilla) return;
    var exactas = {};
    (d.plantillaExacta || []).forEach(function (p) { exactas[p[0]] = p[1]; });
    var w = document.createTreeWalker(dc, NodeFilter.SHOW_TEXT, null), n, nodos = [];
    while ((n = w.nextNode())) if (n.parentNode.nodeName !== 'SCRIPT') nodos.push(n);
    nodos.forEach(function (t) {
      var s = t.nodeValue, limpio = s.trim();
      if (!limpio) return;
      if (exactas.hasOwnProperty(limpio)) { t.nodeValue = s.replace(limpio, exactas[limpio]); return; }
      var r = reemplazar(s, d.plantilla);
      if (r !== s) t.nodeValue = r;
    });
    ['aria-label', 'title', 'placeholder'].forEach(function (a) {
      dc.querySelectorAll('[' + a + ']').forEach(function (el) {
        var v = el.getAttribute(a), r = reemplazar(v, d.plantilla);
        if (r !== v) el.setAttribute(a, r);
      });
    });
    var sc = document.querySelector('script[data-dc-script]');   // va después de </x-dc>, no dentro
    if (sc && d.codigo) sc.textContent = reemplazar(sc.textContent, d.codigo);
  }

  // ¿Queda texto en español? (tildes, ñ, ¿¡ o palabras muy frecuentes)
  var ES = /[áéíóúñ¿¡]|\b(de|del|la|el|los|las|su|sus|con|por|para|fuera|rango|lectura|sueño|valor|que|en|una?|sin|seguidas?)\b/i;

  // Texto libre del backend (recomendaciones, interpretaciones, estados). Si no se puede traducir entero, devuelve un respaldo.
  function backend(texto, respaldo) {
    if (idioma !== 'en' || texto == null) return texto;
    var s = String(texto), d = D();
    if (!d.backend) return respaldo != null ? respaldo : s;
    var r = s;
    d.backend.forEach(function (p) {
      var es = p[0], re = new RegExp('(^|[^\\wáéíóúñ])' + es.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?=$|[^\\wáéíóúñ])', 'g');
      if (/^\s|\s$/.test(es)) r = r.split(es).join(p[1]);   // conectores (" de ", " y ")
      else r = r.replace(re, function (m, pre) { return pre + p[1]; });
    });
    if (!ES.test(r)) return r;
    return respaldo != null ? respaldo : 'Health notice (details available in Spanish).';
  }

  function nombreVariable(v) {
    if (!v) return 'Health';
    var t = backend(String(v), String(v).replace(/_/g, ' '));
    return t.charAt(0).toUpperCase() + t.slice(1);
  }

  // Evento/notificación del backend {codigo, mensaje, variable}: glosario y, si queda español, el texto por código.
  function evento(e) {
    if (!e) return '';
    if (idioma !== 'en') return e.mensaje;
    var d = D(), v = nombreVariable(e.variable);
    var porCodigo = ((d.porCodigo || {})[String(e.codigo)] || d.generico || '{v}: needs attention').replace('{v}', v);
    return backend(e.mensaje, porCodigo);
  }

  function cambiar(nuevo) {
    if (nuevo !== 'es' && nuevo !== 'en') return;
    try { localStorage.setItem(CLAVE, nuevo); } catch (e) { }
    try { if (window.OrbitalVoz) window.OrbitalVoz.voz.callar(); } catch (e) { }
    var u = new URL(location.href); u.searchParams.delete('idioma');
    location.replace(u.toString());   // la plantilla se traduce antes del arranque: hay que recargar
  }

  window.OrbitalI18n = {
    idioma: idioma,
    cambiar: cambiar,
    alternar: function () { cambiar(idioma === 'en' ? 'es' : 'en'); },
    backend: backend,
    evento: evento
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', aplicar);
  else aplicar();
})();
