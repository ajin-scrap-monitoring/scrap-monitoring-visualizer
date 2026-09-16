ARG PYTHON_IMAGE=python@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:b485bd65cc2cf1c9a93b3554012c9c3778cf7b1b5fd3d3096ce9e1226c97e1e6

FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS builder

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
COPY contracts/ contracts/

RUN uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libegl1=1.6.0-1 \
        libgl1=1.6.0-1 \
        libosmesa6=22.3.6-1+deb12u2 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 visualizer \
    && useradd --uid 10001 --gid visualizer --no-create-home --home-dir /tmp visualizer \
    && mkdir /app \
    && chown visualizer:visualizer /app

COPY --from=builder --chown=visualizer:visualizer /app /app
COPY --chown=visualizer:visualizer THIRD_PARTY_NOTICES.md /app/THIRD_PARTY_NOTICES.md

ARG BUILD_REVISION=unknown
ARG BUILD_VERSION=2.0.1

LABEL org.opencontainers.image.description="Headless 3D visualizer for Scrap Monitoring LiDAR observations" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/ajin-scrap-monitoring/scrap-monitoring-visualizer" \
      org.opencontainers.image.title="Scrap Monitoring Visualizer" \
      org.opencontainers.image.version="${BUILD_VERSION}"

ENV HOME=/tmp \
    LIBGL_ALWAYS_SOFTWARE=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYVISTA_OFF_SCREEN=true \
    VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow \
    XDG_CACHE_HOME=/tmp/cache

WORKDIR /app
USER 10001:10001
STOPSIGNAL SIGTERM

EXPOSE 17000/tcp 18000/tcp

ENTRYPOINT ["scrap-monitoring-visualizer"]
CMD ["--help"]
