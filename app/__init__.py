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

# No import-time side effects: the ADK App is built lazily in app.agent
# (importing it eagerly here ran build_storage() -> created/migrated the SQLite
# DB merely by importing any app.* submodule). ADK's AgentLoader imports
# app.agent and reads its lazy `app`/`root_agent` attributes directly.
