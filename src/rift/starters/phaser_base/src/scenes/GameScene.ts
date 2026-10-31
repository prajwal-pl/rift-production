import Phaser from "phaser";
import { bridge } from "../bridge";
import { CONFIG } from "../config";

// PLACEHOLDER gameplay: replace with the real game described in the GDD.
export class GameScene extends Phaser.Scene {
  private player!: Phaser.Physics.Arcade.Sprite;
  private cursors!: Phaser.Types.Input.Keyboard.CursorKeys;
  private score = 0;

  constructor() {
    super("Game");
  }

  create(): void {
    this.score = 0;
    const size = CONFIG.player.size;
    if (!this.textures.exists("player")) {
      const g = this.make.graphics({ x: 0, y: 0 }, false);
      g.fillStyle(CONFIG.player.color, 1);
      g.fillRect(0, 0, size, size);
      g.generateTexture("player", size, size);
      g.destroy();
    }
    this.player = this.physics.add.sprite(CONFIG.width / 2, CONFIG.height / 2, "player");
    this.player.setCollideWorldBounds(true);
    this.cursors = this.input.keyboard!.createCursorKeys();
    this.input.keyboard!.addCapture("UP,DOWN,LEFT,RIGHT,SPACE");
    bridge.set({ scene: "Game", score: 0, lives: 3, gameOver: false, lose: false, win: false });
  }

  override update(): void {
    const speed = CONFIG.player.speed;
    this.player.setVelocity(
      (this.cursors.right.isDown ? 1 : 0) * speed - (this.cursors.left.isDown ? 1 : 0) * speed,
      (this.cursors.down.isDown ? 1 : 0) * speed - (this.cursors.up.isDown ? 1 : 0) * speed,
    );
    bridge.set({ score: this.score, playerX: this.player.x, playerY: this.player.y });
  }
}
