FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa poppler-utils libmagic1 libreoffice-writer libreoffice-calc && rm -rf /var/lib/apt/lists/*
COPY requirements.lock ./
RUN --mount=type=secret,id=environment_ca \
    if [ -f /run/secrets/environment_ca ]; then export PIP_CERT=/run/secrets/environment_ca; fi; \
    pip install --require-hashes -r requirements.lock
RUN groupadd --gid 10001 workflow && useradd --uid 10001 --gid workflow --create-home workflow
COPY --chown=workflow:workflow . .
USER workflow
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
