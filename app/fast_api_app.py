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

"""ADK deployment entrypoint (NOT the product REST API).

This module exposes the ADK ``App``/agent over HTTP via
``google.adk.cli.fast_api.get_fast_api_app`` so the agent can be served on
Agent Engine / Cloud Run with the ADK web UI, session/artifact services, and
the ``/feedback`` endpoint. It is the surface the ADK deployment tooling
(``agents-cli deploy``, Dockerfile) targets.

The canonical product REST API (``/api/...`` — dashboard, runs, news,
sources, watchlist, resolve) lives in ``app/api/app.py`` ``create_app()`` and
is what ``catchup serve`` runs. The two surfaces are intentionally distinct:
this one wraps the *agent* for managed-runtime deployment; the other serves
the *application's* HTTP API. They share no routes, so they cannot silently
diverge.
"""

import os

import google.auth
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from app.api.app import register_product_routes
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback
from app.core.config import Settings

setup_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
# Single source of truth for CORS origins: Settings.allow_origins (ALLOW_ORIGINS
# env, comma-split, trimmed). Passed to get_fast_api_app so ADK's CORS AND its
# origin-check middleware both honor the same allowlist as the product API.
_settings = Settings()
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


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

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
