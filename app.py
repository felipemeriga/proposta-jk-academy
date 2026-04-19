"""Servidor web para gerar a Proposta JK Academy a partir do formulário.

Rotas:
    GET  /          → devolve o formulário (formulario.html)
    POST /gerar     → recebe JSON com os campos e devolve o PDF pronto

Rodar localmente:

    uv run --with fastapi --with uvicorn --with pymupdf \
        uvicorn app:app --reload

Ou, com pip:

    pip install -r requirements.txt
    uvicorn app:app --reload
"""

from __future__ import annotations

import io
import logging
import os
import traceback
import unicodedata
from datetime import datetime

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from substituir_campos import TEMPLATE_PDF, generate_pdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FORM_HTML = os.path.join(BASE_DIR, "formulario.html")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("proposta")

app = FastAPI(title="Gerador de Proposta JK Academy")

# Log o que está na pasta /app quando subir, pra facilitar debug em produção.
logger.info("BASE_DIR=%s", BASE_DIR)
logger.info("Template existe? %s (%s)", os.path.exists(TEMPLATE_PDF), TEMPLATE_PDF)
try:
    logger.info("Conteúdo de %s: %s", BASE_DIR, sorted(os.listdir(BASE_DIR)))
except Exception:  # noqa: BLE001
    logger.exception("Não consegui listar BASE_DIR")


class Campos(BaseModel):
    """Schema dos campos aceitos pelo gerador. Todos opcionais — campos vazios
    mantêm o placeholder original no PDF."""
    text_1: str = ""
    metodo: str = ""
    lista: str = ""
    conclusao: str = ""
    carga_horaria: str = ""
    data: str = ""
    horario: str = ""
    local: str = ""
    pessoas: str = ""

    class Config:
        # Aceita também as chaves com hífen usadas no formulário.
        populate_by_name = True
        # Pydantic v2: permite alias por campo
        extra = "ignore"


# Aliases com hífen (como estão no formulário HTML e no template).
FIELD_ALIASES = {
    "text-1": "text_1",
    "carga-horaria": "carga_horaria",
}


def _slugify(value: str) -> str:
    """Remove acentos/espaços para montar nome de arquivo seguro."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    out = []
    for ch in normalized:
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_/":
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.lower()


@app.get("/", response_class=FileResponse)
def form():
    """Serve o formulário."""
    return FileResponse(FORM_HTML, media_type="text/html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/gerar")
async def gerar(payload: dict = Body(...)):
    """Gera o PDF a partir do JSON do formulário e devolve como download."""
    if not isinstance(payload, dict):
        raise HTTPException(400, "Payload deve ser um objeto JSON")

    # Normaliza chaves: o formulário manda "text-1" / "carga-horaria";
    # o script usa exatamente esses nomes para casar com os placeholders do PDF.
    values = {str(k): ("" if v is None else str(v)) for k, v in payload.items()}
    logger.info("POST /gerar chaves=%s", sorted(values.keys()))

    if not os.path.exists(TEMPLATE_PDF):
        msg = f"Template não encontrado em {TEMPLATE_PDF}"
        logger.error(msg)
        raise HTTPException(500, msg)

    try:
        pdf_bytes = generate_pdf(values)
    except Exception as e:  # noqa: BLE001
        tb = traceback.format_exc()
        logger.error("Falha ao gerar PDF:\n%s", tb)
        raise HTTPException(500, f"{type(e).__name__}: {e}") from e
    finally:
        # Força GC após cada request (o pymupdf deixa muito objeto C++ na heap).
        import gc
        gc.collect()

    # Nome amigável para download (inclui data e, se houver, o local).
    today = datetime.now().strftime("%Y-%m-%d")
    local_slug = _slugify(values.get("local", ""))
    parts = ["Proposta-K-Academy", today]
    if local_slug:
        parts.append(local_slug)
    filename = "-".join(parts) + ".pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
