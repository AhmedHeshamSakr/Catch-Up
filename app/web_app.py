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

"""Cloud Run PRODUCT entrypoint — the single-port product app (console + /api).

This is the public product image's ASGI app. Unlike ``app/fast_api_app.py`` (the
ADK Agent Engine surface, which also exposes ADK-native routes like ``/run`` and
session/eval endpoints), this serves ONLY:
  - the built Next.js console (when ``frontend/out`` exists), and
  - the product ``/api/*`` routes (all key-guarded when API_KEY is set).

There are NO ADK-native routes here, so there is no unauthenticated agent
surface. Cloud Run binds ``0.0.0.0``, so we fail closed: ``API_KEY`` MUST be set
(``create_app``'s own guard checks ``settings.app_host``, which is loopback by
default and would not catch the container bind — hence the explicit check here).
"""
from __future__ import annotations

from app.api.app import create_app
from app.core.config import Settings

# _env_file=None: read config ONLY from the runtime environment (Cloud Run /
# Secret Manager), never a dotenv baked into the image — defense-in-depth behind
# .dockerignore excluding app/.env from the build context.
_settings = Settings(_env_file=None)
if not _settings.api_key:
    raise RuntimeError(
        "app.web_app is the network-exposed Cloud Run product surface and "
        "requires API_KEY. Set the API_KEY env var (Secret Manager in prod)."
    )

app = create_app(_settings)
