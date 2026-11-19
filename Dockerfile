# Image for the scheduled collector job.
FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim
RUN useradd --system --no-create-home --uid 10001 collector
COPY --from=build /app/.venv /app/.venv
# psycopg's bundled OpenSSL looks for trusted roots under its own build prefix, which
# does not exist here; this points sslrootcert=system at Debian's bundle instead.
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
USER collector
ENTRYPOINT ["gridcast-collect"]
