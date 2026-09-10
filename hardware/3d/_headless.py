"""Headless Chromium plumbing shared by verify_model.py, verify_drone.py and render.py.

The pages load three.js from cdnjs. Some sandboxes (this one included) put
outbound HTTPS through a proxy whose CA Chromium does not trust, so the CDN
script silently fails and every page reports "THREE is not defined". The fix
is to fetch three.min.js once with the tools that DO honour the proxy and
substitute a file:// path into a temporary copy of the page. The committed
pages stay self-contained and CDN-based for a normal browser.
"""
import glob
import os
import pathlib
import shutil
import ssl
import subprocess
import tempfile
import urllib.request

THREE_URL = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
ERROR_HOOK = (
    "<script>window.__err=[];"
    "window.addEventListener('error',function(e){window.__err.push(String(e.message)+' @'+e.lineno);"
    "document.title='JSERROR: '+window.__err.join(' | ');});"
    "window.addEventListener('unhandledrejection',function(e){"
    "window.__err.push(String(e.reason));"
    "document.title='JSERROR: '+window.__err.join(' | ');});</script>"
)
FLAGS = ["--headless=new", "--no-sandbox", "--disable-gpu", "--use-gl=swiftshader",
         "--enable-unsafe-swiftshader", "--hide-scrollbars"]


def find_browser():
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"):
        if pathlib.Path(p).exists():
            return p
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), "/opt/pw-browsers",
             os.path.expanduser("~/.cache/ms-playwright")]
    for r in roots:
        if not r:
            continue
        for p in sorted(glob.glob(os.path.join(r, "chromium-*", "chrome-linux*", "chrome")), reverse=True):
            return p
    return shutil.which("chromium") or shutil.which("google-chrome")


def local_three():
    """A cached copy of three.min.js, or None if it cannot be fetched."""
    cache = pathlib.Path(tempfile.gettempdir()) / "three.r128.min.js"
    if cache.exists() and cache.stat().st_size > 400_000:
        return cache
    ctx = ssl.create_default_context()
    for ca in (os.environ.get("SSL_CERT_FILE"), os.environ.get("REQUESTS_CA_BUNDLE"),
               "/root/.ccr/ca-bundle.crt"):
        if ca and pathlib.Path(ca).exists():
            ctx.load_verify_locations(ca)
    try:
        with urllib.request.urlopen(THREE_URL, context=ctx, timeout=60) as r:
            cache.write_bytes(r.read())
    except Exception:
        try:
            subprocess.run(["curl", "-sS", "-o", str(cache), THREE_URL], check=True, timeout=120)
        except Exception:
            return None
    return cache if cache.exists() and cache.stat().st_size > 400_000 else None


def probe_copy(html_path, tmpdir, hook=True):
    """Write a temp copy of the page with the error hook and a local three.js."""
    src = pathlib.Path(html_path).read_text(encoding="utf-8")
    if hook:
        src = src.replace("<script src=", ERROR_HOOK + "\n<script src=", 1)
    three = local_three()
    if three:
        src = src.replace(THREE_URL, three.as_uri())
    out = pathlib.Path(tmpdir) / (pathlib.Path(html_path).stem + ".probe.html")
    out.write_text(src, encoding="utf-8")
    return out, bool(three)


def dump_title(browser, page_uri, tmpdir, timeout=300):
    out = subprocess.run([browser, *FLAGS, "--user-data-dir=%s" % (pathlib.Path(tmpdir) / "p"),
                          "--dump-dom", page_uri], capture_output=True, text=True,
                         timeout=timeout, encoding="utf-8", errors="replace").stdout or ""
    return out.split("</title>")[0].split("<title>")[-1], out


def screenshot(browser, page_uri, png, tmpdir, size=(1600, 1000), timeout=300):
    subprocess.run([browser, *FLAGS, "--user-data-dir=%s" % (pathlib.Path(tmpdir) / "p"),
                    "--window-size=%d,%d" % size, "--screenshot=%s" % png, page_uri],
                   capture_output=True, text=True, timeout=timeout)
    return pathlib.Path(png).exists()
