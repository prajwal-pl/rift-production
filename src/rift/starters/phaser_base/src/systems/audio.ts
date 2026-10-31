// Tiny WebAudio synth. No audio files. The AudioContext is created lazily on the first user
// gesture (browsers block audio before that). Every call is wrapped so audio can never crash the game.

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let muted = false;

export function unlockAudio(): void {
  try {
    if (!ctx) {
      ctx = new AudioContext();
      master = ctx.createGain();
      master.gain.value = muted ? 0 : 1;
      master.connect(ctx.destination);
    }
    if (ctx.state === "suspended") void ctx.resume();
  } catch {
    /* audio unavailable: ignore */
  }
}

export function toggleMute(): boolean {
  muted = !muted;
  if (master) master.gain.value = muted ? 0 : 1;
  return muted;
}

export function isMuted(): boolean {
  return muted;
}

export function blip(
  freqStart: number,
  freqEnd: number,
  durationMs: number,
  type: OscillatorType = "square",
  volume = 0.1,
): void {
  try {
    if (!ctx || !master) return;
    const t = ctx.currentTime;
    const dur = durationMs / 1000;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freqStart, t);
    osc.frequency.exponentialRampToValueAtTime(Math.max(freqEnd, 1), t + dur);
    gain.gain.setValueAtTime(volume, t);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(gain).connect(master);
    osc.start(t);
    osc.stop(t + dur);
  } catch {
    /* ignore */
  }
}
