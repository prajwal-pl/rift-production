"""Playwright verification harness executed INSIDE the Daytona sandbox as `/workspace/verify_game.py`.

Can be imported on the host for `HARNESS_SCRIPT` (the source string uploaded into the sandbox) or
executed directly with `python3 /workspace/verify_game.py` inside the sandbox container.
"""

from pathlib import Path

HARNESS_SCRIPT: str = '''\
import asyncio
import functools
import http.server
import json
import os
import socketserver
import threading
from pathlib import Path


def start_static_server(directory: str, port: int = 4173) -> tuple[socketserver.TCPServer, int]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    except OSError:
        httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    actual_port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, actual_port


async def verify_built_game(dist_dir: str = "/workspace/dist") -> dict:
    from playwright.async_api import async_playwright

    server, port = start_static_server(dist_dir)
    console_errors: list[str] = []
    shots: list[str] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = await browser.new_page(viewport={"width": 960, "height": 540})

            page.on("pageerror", lambda exc: console_errors.append(str(exc)))
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text)
                if msg.type == "error"
                else None,
            )

            await page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="networkidle")

            canvas_count = await page.locator("canvas").count()
            await page.wait_for_function("() => window.__RIFT__?.ready === true", timeout=5000)

            state_t0 = await page.evaluate("() => window.__RIFT__.state()")
            shot_t0 = "/workspace/screenshot_t0.png"
            await page.screenshot(path=shot_t0)
            if Path(shot_t0).is_file():
                shots.append(shot_t0)

            # Trigger start input (Space / click) to enter GameScene, then hold ArrowRight
            await page.keyboard.press("Space")
            await page.wait_for_timeout(150)
            await page.keyboard.down("ArrowRight")
            await page.wait_for_timeout(350)
            await page.keyboard.up("ArrowRight")

            state_t1 = await page.evaluate("() => window.__RIFT__.state()")
            bridge_errors = await page.evaluate("() => window.__RIFT__?.errors ?? []")
            if isinstance(bridge_errors, list):
                console_errors.extend(str(e) for e in bridge_errors)

            shot_t1 = "/workspace/screenshot_t1.png"
            await page.screenshot(path=shot_t1)
            if Path(shot_t1).is_file():
                shots.append(shot_t1)

            await browser.close()

        interactive = state_t0 != state_t1
        boots = len(console_errors) == 0 and canvas_count > 0
        return {
            "passed": boots,
            "boots": boots,
            "canvas_present": canvas_count > 0,
            "interactive": interactive,
            "errors": console_errors,
            "screenshots": shots,
            "state_t0": state_t0,
            "state_t1": state_t1,
        }
    except Exception as exc:
        console_errors.append(f"Runtime harness exception: {exc}")
        return {
            "passed": False,
            "boots": False,
            "canvas_present": False,
            "interactive": False,
            "errors": console_errors,
            "screenshots": shots,
            "state_t0": None,
            "state_t1": None,
        }
    finally:
        server.shutdown()


if __name__ == "__main__":
    verdict = asyncio.run(verify_built_game(os.environ.get("RIFT_DIST_DIR", "/workspace/dist")))
    print(json.dumps(verdict))
'''

if __name__ == "__main__":
    exec(compile(HARNESS_SCRIPT, Path(__file__).name, "exec"))
