import Phaser from "phaser";
import { bridge } from "../bridge";
import { CONFIG } from "../config";

export class GameOverScene extends Phaser.Scene {
  constructor() {
    super("GameOver");
  }

  create(data: { score?: number }): void {
    const { width, height } = CONFIG;
    this.add
      .text(width / 2, height / 2, `GAME OVER\nScore ${data.score ?? 0}\nPress R to restart`, {
        fontFamily: "monospace",
        fontSize: "32px",
        color: CONFIG.colors.text,
        align: "center",
      })
      .setOrigin(0.5);
    this.input.keyboard?.once("keydown-R", () => this.scene.start("Game"));
    bridge.set({ scene: "GameOver", gameOver: true, lose: true, score: data.score ?? 0 });
  }
}
