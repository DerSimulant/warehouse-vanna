// src/lib/tts.ts
export function speak(text: string) {
  if (!text) return;
  try {
    const synth = window.speechSynthesis;
    if (!synth) {
      console.warn("SpeechSynthesis not available");
      return;
    }
    // Cancel laufende Ausgaben (wichtig bei Folgefragen)
    synth.cancel();
    const uttr = new SpeechSynthesisUtterance(text);
    uttr.rate = 1.0;     // optional: 0.8–1.2 im Lager testen
    uttr.pitch = 1.0;
    uttr.lang = "de-DE"; // ggf. "en-US"
    synth.speak(uttr);
  } catch (e) {
    console.warn("TTS error", e);
  }
}
