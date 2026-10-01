"""Render the load-runner video and its stills from video/presentation.html.

    uv run --with playwright python video/render.py            # video/load-runner.mp4
    uv run --with playwright python video/render.py --stills   # docs/assets/*.png
    uv run --with playwright python video/render.py --frames 3,46,55.5   # video/build/frame-*.png

Serves the repository over a local HTTP server, opens the page in headless Chromium, and draws every
frame by setting body[data-t] (ms) and dispatching "render". Frames are piped to ffmpeg as PNGs and
muxed with video/build/music.wav (rendered first by video/music.py if missing). Chromium for
Playwright: `uv run --with playwright playwright install chromium`.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / "video"
BUILD = VIDEO / "build"
MUSIC = BUILD / "music.wav"
OUT = VIDEO / "load-runner.mp4"
ASSETS = ROOT / "docs" / "assets"
FPS = 30
DURATION = 73.6
WIDTH, HEIGHT = 1280, 720
VIDEO_SCALE, STILL_SCALE = 1.5, 2
STILL_FRAMES = {"title": 5.0, "poster": 55.5}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def serve() -> Iterator[str]:
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def open_presentation(browser, base: str, scale: float) -> Page:
    page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=scale)
    page.goto(f"{base}/video/presentation.html")
    page.evaluate("document.fonts.ready")
    return page


def frame_png(page: Page, seconds: float) -> bytes:
    page.evaluate(
        "t => { document.body.dataset.t = String(t); document.dispatchEvent(new Event('render')); }",
        round(seconds * 1000, 3),
    )
    return page.screenshot(clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT}, type="png")


def ensure_music() -> None:
    if MUSIC.exists():
        return
    BUILD.mkdir(parents=True, exist_ok=True)
    music = ["uv", "run", "--with", "numpy", "--with", "scipy", "python", str(VIDEO / "music.py"), str(MUSIC)]
    subprocess.run(music, check=True, cwd=ROOT)


def render_video(browser, base: str) -> None:
    ensure_music()
    page = open_presentation(browser, base, VIDEO_SCALE)
    total = round(DURATION * FPS)
    # fmt: off
    ffmpeg = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
        "-i", str(MUSIC),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "18", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{DURATION}", "-movflags", "+faststart",
        str(OUT),
    ]
    # fmt: on
    encoder = subprocess.Popen(ffmpeg, stdin=subprocess.PIPE)
    assert encoder.stdin is not None
    for i in range(total):
        encoder.stdin.write(frame_png(page, i / FPS))
        if i % FPS == 0:
            print(f"\r{i / FPS:5.1f} / {DURATION} s", end="", file=sys.stderr, flush=True)
    encoder.stdin.close()
    if encoder.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print(f"\nwrote {OUT.relative_to(ROOT)}", file=sys.stderr)


def render_stills(browser, base: str) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=STILL_SCALE)
    for name in ("loop", "bus", "thread"):
        for theme in ("light", "dark"):
            page.goto(f"{base}/video/diagrams.html?d={name}&theme={theme}")
            page.wait_for_selector("body[data-ready]")
            path = ASSETS / f"diagram-{name}-{theme}.png"
            page.locator("#shot").screenshot(path=path)
            print(f"wrote {path.relative_to(ROOT)}", file=sys.stderr)
    page = open_presentation(browser, base, STILL_SCALE)
    page.evaluate("document.body.dataset.still = ''")  # static images never blink
    for name, seconds in STILL_FRAMES.items():
        path = ASSETS / f"{name}.png"
        path.write_bytes(frame_png(page, seconds))
        print(f"wrote {path.relative_to(ROOT)}", file=sys.stderr)


def render_frames(browser, base: str, times: list[float]) -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    page = open_presentation(browser, base, VIDEO_SCALE)
    for seconds in times:
        path = BUILD / f"frame-{round(seconds * 1000):05d}.png"
        path.write_bytes(frame_png(page, seconds))
        print(f"wrote {path.relative_to(ROOT)}", file=sys.stderr)


def main() -> None:
    formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=formatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--stills", action="store_true", help="export the diagrams, poster, and title PNGs")
    group.add_argument("--frames", help="comma-separated times in seconds to export as review PNGs")
    args = parser.parse_args()
    with serve() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            if args.stills:
                render_stills(browser, base)
            elif args.frames:
                render_frames(browser, base, [float(t) for t in args.frames.split(",")])
            else:
                render_video(browser, base)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
