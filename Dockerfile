# --- librespot (Rust): the Spotify Connect receiver. See LIBRESPOT_RUST_PLAN.md ---
#
# Built from source because the project publishes no binaries (the v0.8.0
# GitHub release has zero assets).
#
# The base MUST match the runtime image's Debian release. rust:slim is bookworm
# (glibc 2.36) and its output dies here with "GLIBC_2.32/2.33/2.34 not found" --
# verified 2026-08-15. python:3.9.13-slim is bullseye, glibc 2.31.
#
#   --locked        without it librespot-core's build script fails to compile:
#                   vergen-gitcl floats to 1.0.8 and breaks its own trait bound.
#   --no-default-features   drops the rodio/ALSA backend. The pipe backend we
#                   use is not feature-gated, so it survives (`--backend ?`).
#   --features rustls-tls-webpki-roots   --no-default-features also strips TLS,
#                   and librespot-oauth has a compile-time check demanding one
#                   of the three TLS features. rustls keeps OpenSSL out of both
#                   images, which also avoids a libssl3-vs-bullseye problem.
#   CARGO_BUILD_JOBS=1   this host is 2 cores / 3 GB and runs the live bot; a
#                   parallel rustc invites the OOM killer, which would pick the
#                   bot (it carries automod/nsfw.py's ML imports).
#
# This stage is cached; it only recompiles when these lines change.
FROM rust:slim-bullseye AS librespot-build
ENV CARGO_BUILD_JOBS=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN cargo install librespot --version 0.8.0 --locked \
    --no-default-features --features rustls-tls-webpki-roots \
    --root /out

FROM python:3.9.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    python3-dev \
    libpq-dev \
    libpq5 \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=librespot-build /out/bin/librespot /usr/local/bin/librespot

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD []
