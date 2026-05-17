FROM python:3.10-slim
WORKDIR /app
# Sprint 16 (P2): WeasyPrint native deps (GObject/Pango/Cairo/gdk-pixbuf stack).
# python:3.10-slim is Debian bookworm and ships none of these → import-time
# OSError "cannot load library 'libgobject-2.0-0'". Additive apt layer ONLY,
# placed before the pip step so it is its own cacheable layer unaffected by
# app-code changes. --no-install-recommends + same-RUN apt-list cleanup keep
# the image bounded (~<0.12 GB; no SYS-BL-01 regression). bookworm gdk-pixbuf
# runtime package is libgdk-pixbuf-2.0-0. libgobject-2.0-0 arrives transitively
# via libglib2.0-0 (pulled by libpango/libgdk-pixbuf).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libffi-dev \
        shared-mime-info \
        fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --prefer-binary -r requirements.txt
COPY . .
