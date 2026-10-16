# One image for both services:
#   web     the default command: migrations, then gunicorn
#   worker  command: python manage.py process_receipts
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # EasyOCR models are downloaded here during the build, not when the worker starts.
    EASYOCR_MODULE_PATH=/opt/easyocr \
    MEDIA_ROOT=/app/media \
    PORT=8000

# Shared libraries OpenCV needs, nothing else.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch and torchvision first (the default Linux build pulls in several GB of CUDA
# libraries), at the versions pinned in requirements.txt. Then everything else; the
# installed 2.14.1+cpu already satisfies torch==2.14.1. tr strips Windows line endings (CRLF),
# which would otherwise end up inside the package names.
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        $(grep -E '^(torch|torchvision)==' requirements.txt | tr -d '\r') \
    && pip install -r requirements.txt

# Run as a non-root user. The media folder must exist and belong to it, so a volume
# mounted there is writable.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /opt/easyocr /app/media /app/staticfiles \
    && chown app:app /opt/easyocr /app/media /app/staticfiles

USER app

# The Arabic + English models, exactly as expenses/ai/ocr.py loads them. Kept before the
# COPY of the code so code changes do not download them again.
RUN python -c "import easyocr; easyocr.Reader(['ar', 'en'], gpu=False)"

COPY --chown=app:app . .

# Static files with hashed names for WhiteNoise. The settings need a secret key and a
# database configuration to load, but collectstatic uses neither.
RUN SECRET_KEY=collectstatic-only DATABASE_URL=sqlite:////tmp/unused.sqlite3 \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi --workers 2 --timeout 60 --bind 0.0.0.0:${PORT:-8000}"]
