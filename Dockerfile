# --- build: the full image ships gcc, needed because pyswisseph is sdist-only
FROM python:3.12 AS build
RUN pip install --no-cache-dir uv==0.11.32
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev \
    && uv run --no-sync python scripts/fetch_ephemeris.py /app/ephe

# --- runtime
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    SKYCAL_EPHE_PATH=/app/ephe \
    DATABASE_URL=sqlite:////data/calendar.db
WORKDIR /app
COPY --from=build /app /app
EXPOSE 8080
# Single process on purpose: the in-process scheduler must run exactly once.
CMD ["uvicorn", "skycal.api.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
