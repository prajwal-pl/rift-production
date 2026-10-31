// Test bridge read by the automated verifier (Playwright). DO NOT remove or rename keys.
// Game code reports live values with `bridge.set({...})`; the verifier reads `window.__RIFT__`.

export interface RiftState {
  scene: string;
  score: number;
  lives: number;
  win: boolean;
  lose: boolean;
  gameOver: boolean;
  playerX: number;
  playerY: number;
  entities: number;
  [key: string]: unknown;
}

export interface RiftBridge {
  ready: boolean;
  state(): RiftState;
  errors: string[];
}

declare global {
  interface Window {
    __RIFT__: RiftBridge;
  }
}

const live: RiftState = {
  scene: "boot",
  score: 0,
  lives: 0,
  win: false,
  lose: false,
  gameOver: false,
  playerX: 0,
  playerY: 0,
  entities: 0,
};

export const bridge = {
  /** Merge live values (call every frame or on change). */
  set(partial: Partial<RiftState>): void {
    Object.assign(live, partial);
  },
  /** Mark the game as interactive (call once the Title scene exists). */
  markReady(): void {
    window.__RIFT__.ready = true;
  },
  reportError(message: string): void {
    window.__RIFT__.errors.push(message);
  },
};

export function installBridge(): void {
  window.__RIFT__ = {
    ready: false,
    state: () => ({ ...live }),
    errors: [],
  };
  window.addEventListener("error", (e) => bridge.reportError(String(e.message)));
  window.addEventListener("unhandledrejection", (e) =>
    bridge.reportError(`unhandledrejection: ${String(e.reason)}`),
  );
}
