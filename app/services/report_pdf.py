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



def build_zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zip_file:
        for filename, payload in files:
            zip_file.writestr(filename, payload)
    buffer.seek(0)
    return buffer.read()
