from selenium.webdriver.chrome.options import Options


def chrome_options_factory(port: int = 9222, window_size: str = "1920,1080", headless: bool = True):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"--window-size={window_size}")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument(f"--remote-debugging-port={port}")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    return chrome_options


def kill_orphan_chrome(*ports):
    # Only kill Chrome processes using the specific debugging ports we asked for
    try:
        import psutil
    except Exception:
        return

    target_ports = set(ports)
    if not target_ports:
        return

    for proc in psutil.process_iter(["pid", "name"]):
        name = proc.info.get("name") or ""
        if name not in ("chrome", "chromedriver"):
            continue

        cmdline = " ".join(proc.info.get("cmdline") or [])
        if not any(f"--remote-debugging-port={port}" in cmdline for port in target_ports):
            continue

        try:
            proc.kill()
        except Exception:
            pass
