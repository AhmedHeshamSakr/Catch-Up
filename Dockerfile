# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Cloud Run PRODUCT image: serves the Next.js console + the product /api on one
# port via app.web_app (NOT the ADK Agent Engine surface — that path deploys via
# `agents-cli deploy`, which targets app/fast_api_app.py and must run behind
# Cloud Run IAM / IAP). API_KEY must be set at runtime (app.web_app fails closed).

# ---- Stage 1: build the Next.js console (static export -> frontend/out) ----
FROM node:20-slim AS console
WORKDIR /console
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin: the static console calls /api on whatever host serves it.
ENV NEXT_PUBLIC_API_BASE=""
RUN npm run build

# ---- Stage 2: the Python product app ----
FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.8.13

WORKDIR /code

COPY ./pyproject.toml ./README.md ./uv.lock* ./

COPY ./app ./app

# The product /api/sources and /api/watchlist routes read/write config/*.yaml,
# so the deployed container needs them.
COPY ./config ./config

# The built console — create_app() mounts it at / when this directory exists.
# Settings.console_dir defaults to /code/frontend/out (REPO_ROOT/frontend/out).
COPY --from=console /console/out ./frontend/out

# Install base deps + the [firestore] extra so STORAGE_BACKEND=firestore can
# import the client (the extra is optional in pyproject; without it the firestore
# path would fail at import inside the container).
RUN uv sync --frozen --extra firestore

ARG COMMIT_SHA=""
ENV COMMIT_SHA=${COMMIT_SHA}

ARG AGENT_VERSION=0.0.0
ENV AGENT_VERSION=${AGENT_VERSION}

# Cloud Run injects $PORT (defaults to 8080). API_KEY MUST be set or app.web_app
# refuses to start (it is the network-exposed product surface).
EXPOSE 8080
CMD ["sh", "-c", "uv run uvicorn app.web_app:app --host 0.0.0.0 --port ${PORT:-8080}"]
