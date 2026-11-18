"""Start a dedicated, visible browser for interactive crawler login."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

CDP = "http://127.0.0.1:9222"
PROFILE = Path(__file__).resolve().parents[2] / "data" / "crawler-chrome"


def ready():
    try:
        with urllib.request.urlopen(CDP + "/json/version", timeout=2) as response:
            return bool(json.load(response).get("webSocketDebuggerUrl"))
    except (OSError, ValueError):
        return False


def find_browser():
    override = os.environ.get("CRAWLER_BROWSER")
    candidates = [override] if override else []
    for root in (os.environ.get("LOCALAPPDATA"), os.environ.get("PROGRAMFILES"),
                 os.environ.get("PROGRAMFILES(X86)")):
        if root:
            candidates.extend(str(Path(root) / rel) for rel in (
                "Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"))
    candidates.extend(shutil.which(name) for name in ("google-chrome", "chromium", "chromium-browser", "msedge"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError("找不到 Chrome/Edge；请设置 CRAWLER_BROWSER 为浏览器可执行文件路径。")


def ensure_browser(url="https://www.nowcoder.com", timeout=30):
    if ready():
        print("[browser] 复用 127.0.0.1:9222", flush=True)
        return
    browser = find_browser()
    PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([browser, "--remote-debugging-port=9222",
                      "--remote-debugging-address=127.0.0.1",
                      "--remote-allow-origins=http://127.0.0.1:9222",
                      f"--user-data-dir={PROFILE}", "--no-first-run", url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("[browser] 已请求打开专用浏览器；如出现登录或验证码，请在该窗口完成。", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready():
            return
        time.sleep(0.5)
    raise RuntimeError("浏览器调试端口未就绪；请检查浏览器是否成功启动。")


if __name__ == "__main__":
    ensure_browser()
