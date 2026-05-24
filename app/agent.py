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

import uuid

from google.adk.apps import App

from app.core.config import Settings
from app.pipeline.agents import build_pipeline
from app.runner import build_storage

_settings = Settings()
root_agent = build_pipeline(_settings, build_storage(_settings), run_id=uuid.uuid4().hex[:12])
app = App(root_agent=root_agent, name="app")
