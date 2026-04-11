from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import Request
from jinja2 import Environment
from weasyprint import HTML, default_url_fetcher

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = PROJECT_ROOT / "app" / "static"
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"


def _local_url_fetcher(url: str):
    if url.startswith("/static/"):
        relative_path = unquote(url.removeprefix("/static/").replace("/", "\\"))
        file_path = STATIC_DIR / Path(relative_path)
        return {"file_obj": file_path.open("rb"), "mime_type": None}

    parsed = urlsplit(url)
    if parsed.scheme in {"http", "https"} and parsed.path.startswith("/static/"):
        relative_path = unquote(parsed.path.removeprefix("/static/").replace("/", "\\"))
        file_path = STATIC_DIR / Path(relative_path)
        return {"file_obj": file_path.open("rb"), "mime_type": None}

    return default_url_fetcher(url)



def render_template_to_pdf_bytes(
    *,
    templates,
    template_name: str,
    context: dict,
    request: Request | None = None,
) -> bytes:
    env: Environment = templates.env
    template = env.get_template(template_name)
    rendered_html = template.render(context)
    base_url = str(request.base_url) if request else TEMPLATES_DIR.as_uri() + "/"
    return HTML(string=rendered_html, base_url=base_url, url_fetcher=_local_url_fetcher).write_pdf()



def build_zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zip_file:
        for filename, payload in files:
            zip_file.writestr(filename, payload)
    buffer.seek(0)
    return buffer.read()
