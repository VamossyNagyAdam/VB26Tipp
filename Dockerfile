# VB26Tipp – Dockerfile a SnapDeploy (vagy bármely Docker-alapú hoszting) számára.
# A lényeg: a libsql==0.1.11 natív (Rust) csomag, ezért a build-környezetbe
# telepítjük a Rust-fordítót és a szükséges rendszereszközöket, hogy biztosan
# leforduljon. Futásidőben ezek már nem kellenek, de a slim képen kis méret marad.

FROM python:3.12-slim

# rendszerszintű build-eszközök a natív csomagokhoz (libsql = Rust)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        pkg-config \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Rust-toolchain telepítése (a libsql fordításához)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# előbb csak a requirements-et másoljuk (jobb build-cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# a teljes alkalmazás
COPY . .

# a SnapDeploy a PORT env változót adja; alapértelmezés 8000, ha nincs megadva
ENV PORT=8000
EXPOSE 8000

# indítás: a $PORT-ot használjuk, hogy a hoszting portjához igazodjunk
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
