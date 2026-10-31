import Phaser from "phaser";
import { bridge } from "../bridge";
import { CONFIG } from "../config";
import { unlockAudio } from "../systems/audio";

export class TitleScene extends Phaser.Scene {
  constructor() {
    super("Title");
  }

  create(): void {
    const { width, height } = CONFIG;
    this.add
      .text(width / 2, height / 2 - 30, "RIFT GAME", {
        fontFamily: "monospace",
        fontSize: "48px",
        color: CONFIG.colors.text,
      })
      .setOrigin(0.5);
    this.add
      .text(width / 2, height / 2 + 40, "Press any key or click to start", {
        fontFamily: "monospace",
        fontSize: "22px",
        color: CONFIG.colors.accent,
      })
      .setOrigin(0.5);

    const start = (): void => {
      unlockAudio(); // first user gesture: audio is allowed from here on
      this.scene.start("Game");
    };
    this.input.keyboard?.once("keydown", start);
    this.input.once("pointerdown", start);

    bridge.set({ scene: "Title", gameOver: false });
    bridge.markReady();
  }
}
