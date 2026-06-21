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

"""ADK Agent Engine deployment entrypoint (NOT the product web app).

This module exposes the ADK ``App``/agent over HTTP via
``google.adk.cli.fast_api.get_fast_api_app`` (the ADK web UI, session/artifact
services, ``/feedback``, and ADK-native routes such as ``/run``). It is the
surface ``agents-cli deploy`` targets for Agent Engine / Gemini Enterprise.

SECURITY — this surface is NOT fully app-key-gated. The product ``/api/*`` routes
are key-guarded (via ``register_product_routes``) and ``/feedback`` is
authenticated, but the ADK-native routes (``/run``, sessions, evals, builder) are
served by ``get_fast_api_app`` without the product API key — that is ADK's model.
Therefore this surface MUST run behind Cloud Run IAM / IAP (require
authentication); never expose it to unauthenticated traffic.

The public PRODUCT web app — Next.js console + ``/api/*`` only, with NO ADK
routes and fully key-guarded — is ``app/web_app.py`` (``create_app()``), which the
Dockerfile builds and Cloud Run serves. ``catchup serve`` runs the same
``create_app()`` locally. The two surfaces share no ADK routes, so they cannot
silently diverge.
"""

import os

import google.auth
from fastapi import Depends, FastAPI
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from app.api.app import _rate_limiter, _require_api_key, register_product_routes
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback
from app.core.config import Settings
from app.services.ratelimit import TokenBucket

# Fail closed BEFORE any GCP side effect: this module is the network-exposed
# deploy surface (Agent Engine / Cloud Run), always bound to 0.0.0.0, so a
# deployed /api/* MUST be authenticated. Checking the key first means a missing
# key raises the intended, clear error even where GCP creds are absent (rather
# than failing inside google.auth.default()/Cloud Logging first).
_settings = Settings()
if not _settings.api_key:
    raise RuntimeError(
        "app.fast_api_app is the deployed surface and requires API_KEY. "
        "Set the API_KEY env var (Secret Manager in prod)."
    )

setup_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
# Single source of truth for CORS origins: Settings.allow_origins (ALLOW_ORIGINS
# env, comma-split, trimmed). Passed to get_fast_api_app so ADK's CORS AND its
# origin-check middleware both honor the same allowlist as the product API.
allow_origins = _settings.allow_origins or None

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=True,
)
app.title = "catch-up"
app.description = "API for interacting with the Agent catch-up"

# Serve the product /api/* routes from this SAME deployed container so a
# deployed Next.js console (lib/api.ts -> /api/*) reaches a real backend.
# No extra CORSMiddleware: ADK's get_fast_api_app already installed CORS +
# origin-check with the same allow_origins above.
register_product_routes(app, _settings)


# Feedback writes to Cloud Logging, so it must be authenticated + rate-limited on
# this network-exposed surface (unauthenticated, it's a log-injection / cost vector).
# Reuses the same tested helpers as the product routes; api_key is guaranteed set
# (the import-time guard above fails closed when it isn't).
_feedback_bucket = TokenBucket(
    rate_per_sec=_settings.rate_limit_refill_per_sec,
    capacity=_settings.rate_limit_burst,
)


@app.post(
    "/feedback",
    dependencies=[
        Depends(_require_api_key(_settings)),
        Depends(_rate_limiter(_feedback_bucket)),
    ],
)
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback (authenticated + rate-limited).

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
