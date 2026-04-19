FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Instala dependências primeiro (aproveita cache do Docker).
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia o app, template, fontes e formulário.
COPY app.py substituir_campos.py formulario.html ./
COPY fonts ./fonts
# Sintaxe JSON-array para lidar com o espaço no nome do arquivo.
COPY ["Template Proposta.pdf", "./"]

EXPOSE 8000

# $PORT é injetado por Render/Fly/Railway; default 8000 em local.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
