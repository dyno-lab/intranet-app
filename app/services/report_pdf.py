from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import Request
from jinja2 import Environment

from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = PROJECT_ROOT / "app" / "static"
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"
STATIC_URL_PATTERN = re.compile(r'(?P<prefix>\b(?:src|href)=([\"\"]))(?P<url>(?:https?://[^\"\']+)?/static/[^\"\']*)(?P<suffix>\2)', re.IGNORECASE)
BASE_TAG_PATTERN = re.compile(r"<head([^>]*)>", re.IGNORECASE)


class PDFBackendUnavailableError(RuntimeError):
    pass


class PDFRenderError(RuntimeError):
    pass


def _resolve_wkhtmltopdf_binary() -> str:
    configured = (settings.WKHTMLTOPDF_PATH or "").strip()
    candidates = [configured] if configured else []
    discovered = shutil.which("wkhtmltopdf")
    if discovered:
        candidates.append(discovered)

    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) or (str(Path(candidate)) if Path(candidate).exists() else None)
        if resolved:
            return resolved

    raise PDFBackendUnavailableError(
        "wkhtmltopdf no está instalado o no se pudo localizar. "
        "Instálalo y configura WKHTMLTOPDF_PATH si no está en PATH."
    )


def _resolve_chromium_pdf_binary() -> str:
    candidates = [
        os.environ.get("EDGE_PATH", ""),
        os.environ.get("CHROME_PATH", ""),
        os.environ.get("CHROMIUM_PATH", ""),
        shutil.which("msedge") or "",
        shutil.which("chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        shutil.which("google-chrome") or "",
    ]
    if os.name == "nt":
        program_files = [
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramFiles(x86)", ""),
            os.environ.get("LocalAppData", ""),
        ]
        for root in program_files:
            if not root:
                continue
            candidates.append(str(Path(root, "Microsoft", "Edge", "Application", "msedge.exe")))
        for root in program_files:
            if not root:
                continue
            candidates.append(str(Path(root, "Google", "Chrome", "Application", "chrome.exe")))

    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) or (str(Path(candidate)) if Path(candidate).exists() else None)
        if resolved:
            return resolved

    raise PDFBackendUnavailableError(
        "No se encontro Microsoft Edge, Google Chrome o Chromium para generar el PDF."
    )



def _file_uri_for_static_url(url: str) -> str:
    parsed = urlsplit(url)
    static_path = parsed.path if parsed.scheme in {"http", "https"} else url
    relative_path = unquote(static_path.removeprefix("/static/").replace("/", os.sep))
    return (STATIC_DIR / Path(relative_path)).resolve().as_uri()



def _rewrite_static_urls(rendered_html: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        url = match.group("url")
        if "/static/" not in url:
            return match.group(0)
        return f"{match.group('prefix')}{_file_uri_for_static_url(url)}{match.group('suffix')}"

    return STATIC_URL_PATTERN.sub(_replace, rendered_html)



def _inject_base_href(rendered_html: str, base_href: str) -> str:
    if "<base " in rendered_html.lower():
        return rendered_html
    return BASE_TAG_PATTERN.sub(lambda match: f'<head{match.group(1)}><base href="{base_href}">', rendered_html, count=1)



def _prepare_html_document(rendered_html: str, request: Request | None = None) -> str:
    base_href = str(request.base_url) if request else TEMPLATES_DIR.resolve().as_uri() + "/"
    html = _inject_base_href(rendered_html, base_href)
    return _rewrite_static_urls(html)


def _inject_chromium_pdf_readiness(rendered_html: str) -> str:
    readiness_script = """
<script>
(function () {
  function waitForImages() {
    return Promise.all(Array.prototype.map.call(document.images || [], function (img) {
      if (img.complete) return Promise.resolve();
      return new Promise(function (resolve) {
        img.addEventListener('load', resolve, { once: true });
        img.addEventListener('error', resolve, { once: true });
      });
    }));
  }

  function waitForFonts() {
    return document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
  }

  Promise.all([waitForImages(), waitForFonts()]).then(function () {
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        document.documentElement.setAttribute('data-pdf-ready', 'true');
      });
    });
  });
})();
</script>
"""
    if "</body>" in rendered_html.lower():
        return re.sub(r"</body>", readiness_script + "</body>", rendered_html, count=1, flags=re.IGNORECASE)
    return rendered_html + readiness_script



def render_template_to_pdf_bytes(
    *,
    templates,
    template_name: str,
    context: dict,
    request: Request | None = None,
    wkhtmltopdf_args: list[str] | None = None,
) -> bytes:
    env: Environment = templates.env
    template = env.get_template(template_name)
    rendered_html = template.render(context)
    prepared_html = _prepare_html_document(rendered_html, request=request)
    wkhtmltopdf_binary = _resolve_wkhtmltopdf_binary()

    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as html_file:
        html_file.write(prepared_html)
        html_path = Path(html_file.name)

    try:
        command = [
            wkhtmltopdf_binary,
            "--enable-local-file-access",
            "--allow", str(STATIC_DIR.resolve()),
            "--encoding", "utf-8",
            "--quiet",
        ]
        if wkhtmltopdf_args:
            command.extend(wkhtmltopdf_args)
        command.extend([str(html_path), "-"])
        result = subprocess.run(command, capture_output=True, check=False)
        if result.returncode != 0:
            stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
            raise PDFRenderError(f"wkhtmltopdf falló al generar el PDF: {stderr or 'sin detalles'}")
        return result.stdout
    finally:
        html_path.unlink(missing_ok=True)


def render_template_to_chromium_pdf_bytes(
    *,
    templates,
    template_name: str,
    context: dict,
    request: Request | None = None,
) -> bytes:
    env: Environment = templates.env
    template = env.get_template(template_name)
    rendered_html = template.render(context)
    prepared_html = _prepare_html_document(_inject_chromium_pdf_readiness(rendered_html), request=request)
    chromium_binary = _resolve_chromium_pdf_binary()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        html_path = tmp_path / "report.html"
        pdf_path = tmp_path / "report.pdf"
        profile_path = tmp_path / "profile"
        html_path.write_text(prepared_html, encoding="utf-8")

        command = [
            chromium_binary,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-default-apps",
            "--hide-scrollbars",
            "--allow-file-access-from-files",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=3000",
            "--print-to-pdf-no-header",
            "--no-pdf-header-footer",
            f"--user-data-dir={profile_path}",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ]
        result = subprocess.run(command, capture_output=True, check=False)
        if result.returncode != 0:
            stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
            raise PDFRenderError(f"Chromium fallo al generar el PDF: {stderr or 'sin detalles'}")
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            raise PDFRenderError("Chromium no produjo un PDF valido.")
        return pdf_path.read_bytes()



def build_zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zip_file:
        for filename, payload in files:
            zip_file.writestr(filename, payload)
    buffer.seek(0)
    return buffer.read()
