FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
ENV UV_LINK_MODE=copy UV_NO_CACHE=1
ARG EXTRA=omni
RUN uv sync --extra $EXTRA \
    && rm -rf /root/.cache /tmp/*

ENV HF_HOME=/models \
    TONI_LANGUAGE=en \
    TONI_OMNI_DEVICE=cuda

ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "toni.cli"]
CMD ["--help"]
