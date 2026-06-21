# ruff: noqa
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
from __future__ import annotations

from app.core.config import Settings


def build_app():
    """Construct the ADK App lazily (NO I/O at import time).

    Building the pipeline calls build_storage(), which opens/migrates the SQLite
    file. Doing that at import would create data/catchup.db merely by importing
    any app.* module (breaks read-only FS, pollutes test collection). ADK's
    AgentLoader accesses ``app``/``root_agent`` via hasattr(), which triggers the
    module ``__getattr__`` below — so the App is built on first real access.
    """
    from google.adk.apps import App

    from app.pipeline.agents import build_pipeline
    from app.runner import build_storage

    settings = Settings()
    return App(root_agent=build_pipeline(settings, build_storage(settings)), name="app")


def __getattr__(name: str):
    if name in ("app", "root_agent"):
        built = build_app()
        value = built if name == "app" else built.root_agent
        globals()[name] = value  # cache: build the App at most once
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
