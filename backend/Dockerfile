FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# P07: DOCX -> PDF conversion (app/assembly/pdf.py) shells out to
# LibreOffice headless -- no pure-Python library converts DOCX to PDF
# faithfully. --no-install-recommends keeps this from pulling in a full
# desktop environment.
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project

COPY . .
RUN uv sync

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
