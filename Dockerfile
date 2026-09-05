# =====================================================================
#  Családi Plex - egyetlen image a frontendhez és a backendhez.
#  Ugyanez az image fut a fejlesztői gépen és a production szerveren is;
#  a különbség kizárólag a .env tartalma.
#  Multi-arch: a base image-ek amd64 és arm64 (Apple Silicon) alatt is futnak.
# =====================================================================

# --- 1. lépés: frontend build ---
FROM node:20-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
# npm ci a lockfile-ból (reprodukálható); ha nincs lock, npm install
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY frontend/ ./
RUN npm run build


# --- 2. lépés: futtatókörnyezet ---
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STATIC_DIR=/app/static \
    DATABASE_PATH=/data/app.db

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/devtools ./devtools

# A Vite build a FastAPI statikus könyvtárába kerül.
COPY --from=frontend /build/dist /app/static

# Nem root felhasználóként futunk.
RUN useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
