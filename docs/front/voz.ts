// Voz del front: lee en voz alta lo que devuelve el backend (respuestas del chat,
// notificaciones, aptitud). Usa la Web Speech API del navegador (speechSynthesis):
// sin dependencias, sin backend y sin internet si se usa una voz local del sistema.
//
// Uso rápido:
//   import { voz, lectorStream, textoNotificacion } from "./voz";
//   voz.hablar("Hola");                       // texto suelto (se encola)
//   const lector = lectorStream();            // chat: lee oración por oración mientras llegan tokens
//   lector.agregar(token); ... lector.fin();
//   voz.hablar(textoNotificacion(n), { interrumpir: n.severidad === "CRITICO" });
//   voz.callar();                             // corta todo
//   voz.activar(false);                       // silenciar (se guarda en localStorage)

const CLAVE = "voz.activa";
const disponible = typeof window !== "undefined" && "speechSynthesis" in window;

let activa = true;
try { activa = localStorage.getItem(CLAVE) !== "0"; } catch { /* sin localStorage */ }

let vozElegida: SpeechSynthesisVoice | null = null;
// Chrome puede liberar el utterance antes de terminar y cortar el audio: se guarda la referencia.
const vivos = new Set<SpeechSynthesisUtterance>();

function elegirVoz() {
  const es = speechSynthesis.getVoices().filter(v => v.lang.toLowerCase().startsWith("es"));
  // Preferir voces locales (funcionan sin internet) y, entre ellas, español de México/Latam.
  const puntos = (v: SpeechSynthesisVoice) =>
    (v.localService ? 4 : 0) + (/es[-_](mx|us|419)/i.test(v.lang) ? 2 : 0) + (v.default ? 1 : 0);
  vozElegida = es.sort((a, b) => puntos(b) - puntos(a))[0] ?? null;
}
if (disponible) {
  elegirVoz();                                              // en Chrome llegan después, de forma asíncrona
  speechSynthesis.addEventListener("voiceschanged", elegirVoz);
}

const NOMBRES: Record<string, string> = {
  spo2: "saturación de oxígeno",
  presion_sistolica: "presión sistólica",
  presion_diastolica: "presión diastólica",
  sueno_latencia: "latencia de sueño",
  sueno_duracion: "duración del sueño",
  sueno_eficiencia: "eficiencia del sueño",
  mmHg: "milímetros de mercurio",
  bpm: "latidos por minuto",
};

/** Deja el texto listo para leerse: sin citas, sin markdown y con los nombres técnicos en claro. */
export function limpiar(texto: string): string {
  return texto
    .replace(/\[[^\]]*\]/g, "")                            // citas: [nasa 2.pdf, pág. 39]
    .replace(/[*#`>|]/g, "")                               // markdown
    .replace(/\b(spo2|presion_sistolica|presion_diastolica|sueno_latencia|sueno_duracion|sueno_eficiencia|mmHg|bpm)\b/gi,
             m => NOMBRES[m] ?? NOMBRES[m.toLowerCase()] ?? m)
    .replace(/(\d)\.(\d)/g, "$1,$2")                       // 97.5 -> "97 coma 5", no "97. 5"
    .replace(/\s*=\s*/g, " ")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export interface OpcionesVoz {
  /** Corta lo que se esté diciendo y vacía la cola antes de hablar (alertas críticas). */
  interrumpir?: boolean;
  /** Velocidad, 0.1 a 10 (1 = normal). */
  velocidad?: number;
}

export const voz = {
  /** false si el navegador no tiene síntesis de voz. */
  disponible,

  get activa() { return activa; },

  /** Enciende o apaga la voz; al apagar se calla de inmediato. Se recuerda entre sesiones. */
  activar(valor: boolean) {
    activa = valor;
    try { localStorage.setItem(CLAVE, valor ? "1" : "0"); } catch { /* sin localStorage */ }
    if (!valor) voz.callar();
  },

  /** true si hay una voz en español instalada (si no, se usa la voz por defecto del sistema). */
  hayVozEnEspanol() { return vozElegida !== null; },

  /** Encola un texto para leerlo en voz alta. */
  hablar(texto: string, opts: OpcionesVoz = {}) {
    if (!disponible || !activa) return;
    const limpio = limpiar(texto);
    if (!limpio) return;
    if (opts.interrumpir) speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(limpio);
    u.lang = vozElegida?.lang ?? "es-MX";
    if (vozElegida) u.voice = vozElegida;
    u.rate = opts.velocidad ?? 1;
    vivos.add(u);
    u.onend = u.onerror = () => vivos.delete(u);
    speechSynthesis.speak(u);
  },

  /** Corta lo que se esté diciendo y vacía la cola. */
  callar() {
    if (!disponible) return;
    speechSynthesis.cancel();
    vivos.clear();
  },
};

/**
 * Lee un texto que llega por partes (eventos `token` de /preguntar/stream).
 * Habla cada oración en cuanto se completa, sin esperar al final de la respuesta.
 */
export function lectorStream(opts: OpcionesVoz = {}) {
  let buf = "";

  // Fin de oración: . ! ? … seguido de espacio. No corta dentro de una cita [ ... ] sin cerrar
  // (p. ej. "[nasa 2.pdf, pág. 39]") ni en decimales (97.5 no lleva espacio después del punto).
  function corte(): number {
    const re = /[.!?…]+\s/g;
    for (let m; (m = re.exec(buf)); ) {
      const fin = m.index + m[0].length;
      const previo = buf.slice(0, fin);
      if (previo.lastIndexOf("[") <= previo.lastIndexOf("]")) return fin;
    }
    return -1;
  }

  return {
    agregar(token: string) {
      buf += token;
      for (let i; (i = corte()) !== -1; ) {
        voz.hablar(buf.slice(0, i), opts);
        buf = buf.slice(i);
      }
    },
    /** Llamar en el evento `fin`: lee lo que quedó sin punto final. */
    fin() {
      voz.hablar(buf, opts);
      buf = "";
    },
    /** Llamar al cancelar la pregunta o en el evento `error`. */
    cancelar() {
      buf = "";
      voz.callar();
    },
  };
}

const SEVERIDAD: Record<string, string> = {
  VIGILAR: "Aviso",
  ALERTA: "Alerta",
  CRITICO: "Alerta crítica",
};

/** Frase hablada para una notificación del stream de salud (evento `notificacion`). */
export function textoNotificacion(n: { usuario: string; severidad: string; mensaje: string }): string {
  return `${SEVERIDAD[n.severidad] ?? "Aviso"}, ${n.usuario}. ${n.mensaje}.`;
}

/** Frase hablada para la respuesta de GET /tripulantes/{id}/aptitud. */
export function textoAptitud(a: { usuario: string; apto: boolean; estado: string; recomendaciones: string[] }): string {
  const base = `${a.usuario}: ${a.apto ? "apto" : "no apto"}. Estado: ${a.estado}.`;
  return a.recomendaciones.length ? `${base} Recomendaciones: ${a.recomendaciones.join(". ")}.` : base;
}
