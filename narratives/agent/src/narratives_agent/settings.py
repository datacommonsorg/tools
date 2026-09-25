# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Environment configuration for the agent.

Every environment variable the package reads is a field of `Settings`, and
`get_settings` returns one validated instance of it, so each variable is read
in one place and normalized the same way for every caller.
"""

import functools
from pathlib import Path
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    ValidationInfo,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# SESSION_LOG_TO_FILE turns file logging on with one of these values, compared
# after stripping and lowercasing, and off with any other value.
_SESSION_LOG_TO_FILE_ON = ("1", "true", "yes")


def _strip_trailing_slashes(value: str) -> str:
    """Returns `value` without trailing slashes."""
    return value.rstrip("/")


def _parse_session_log_to_file(value: bool | str) -> bool:
    """Returns the file-logging flag parsed from `value`.

    Args:
        value: The raw SESSION_LOG_TO_FILE string, or the bool the field's
            default factory computed, which is validated like any input.

    Returns:
        A bool `value` unchanged; otherwise whether the stripped, lowercased
        string is one of `_SESSION_LOG_TO_FILE_ON`.
    """
    if isinstance(value, bool):
        return value
    return value.strip().lower() in _SESSION_LOG_TO_FILE_ON


def _default_static_root(data: dict[str, Any]) -> Path:
    """Returns the `static` directory under the validated `agent_root`."""
    agent_root: Path = data["agent_root"]
    return agent_root / "static"


def _fall_back_to_data_plane_url(value: str, info: ValidationInfo) -> str:
    """Returns `value` without trailing slashes, or else `data_plane_url`.

    The validated `data_plane_url` replaces a value that is empty once its
    trailing slashes are gone, so "/" falls back just as an unset variable does.
    """
    data_plane_url: str = info.data.get("data_plane_url", "")
    return value.rstrip("/") or data_plane_url


def _default_session_log_to_file(data: dict[str, Any]) -> bool:
    """Returns True off Cloud Run, where `k_service` is empty."""
    return not data["k_service"]


# Trailing slashes are stripped from these strings, so a base URL or path
# prefix joins with "/<path>" without doubling the separator.
_NoTrailingSlashStr = Annotated[str, AfterValidator(_strip_trailing_slashes)]


class Settings(BaseSettings):
    """Holds the environment variables the agent reads.

    Each field reads the variable of the same name in upper case. String values
    are stripped of surrounding whitespace, and a variable that is empty or
    only whitespace counts as unset, so the field keeps its default.
    """

    model_config = SettingsConfigDict(str_strip_whitespace=True, frozen=True)

    # The `agent/` directory, where config.json, logs, and the staged SPA
    # live. Set via `AGENT_ROOT` in the container (`Dockerfile`); falls back
    # to three levels above `agent/src/narratives_agent/settings.py` in a
    # local checkout. Anything resolving a path against the agent directory
    # should read this rather than counting parents of its own `__file__`.
    agent_root: Path = Path(__file__).resolve().parents[2]

    # The compiled UI is served from here. The Dockerfile copies the `ui` build
    # to the default, `static` under `agent_root`. Overridable so a local
    # `uv run narratives-agent-dev` can point straight at ui/dist without a
    # container build.
    static_root: Path = Field(default_factory=_default_static_root)

    # The local development server (`uv run narratives-agent-dev`) listens on
    # this port.
    agent_port: int = 5001

    # The agent API is served under this path prefix. The API routers declare
    # their routes at the root (/brand, /chat/stream, /health) and are included
    # under this prefix, since nothing in front of the app plane strips one;
    # that leaves the root free for the SPA. "/" selects the root itself,
    # because an empty variable counts as unset. Brand asset URLs in the
    # branding document are built from the same value.
    agent_api_prefix: _NoTrailingSlashStr = "/agent"

    # CORS allows the comma-separated origins listed here. Left unset, it
    # allows only the local development origins, and none at all on Cloud Run.
    allowed_origin: str = ""

    # Cloud Run sets this to the name of the service. It is empty anywhere
    # else, such as on a developer machine.
    k_service: str = ""

    # Base URL of the data-plane service. Empty means "not split yet" -- the
    # data-plane proxy routes then report a clear 503 instead of proxying to
    # nowhere.
    data_plane_url: _NoTrailingSlashStr = ""

    # Where the BROWSER's data routes go, which is not always where MCP goes.
    #
    # On cdc and dcp one container serves both, so these are the same host and
    # this variable is unset. On the "none" backend they are genuinely two
    # hosts:
    #
    #   api.datacommons.org  the versioned REST API and /mcp -- what the
    #                        agent uses
    #   datacommons.org      the website routes the chart web components
    #                        call: /api/observations/series,
    #                        /api/place/name, /core/api/...
    #
    # Sending chart traffic to the API host returns
    #   {"message":"The current request is not defined by this API.","code":404}
    # from Cloud Endpoints, for every chart, on every turn. The proxy and the
    # auth are both working at that point -- the routes simply do not exist on
    # that host, so nothing renders and nothing looks broken server-side.
    #
    # Falls back to `data_plane_url` so cdc and dcp need no configuration.
    data_plane_web_url: Annotated[
        str, AfterValidator(_fall_back_to_data_plane_url)
    ] = ""

    # "off", compared case-insensitively, stops credentials from being attached
    # to data-plane and MCP requests; any other value, like the default "auto",
    # chooses them by target host.
    data_plane_auth: str = "auto"

    # The agent sends this API key as `X-API-Key` to public Data Commons hosts.
    dc_api_key: str = ""

    # The agent reaches the MCP server at this URL, which takes precedence over
    # `mcp.server_url` in config.json. With neither set, it calls localhost on
    # `mcp_port`.
    mcp_server_url: str = ""

    # The co-located MCP server listens on this port, which the agent calls
    # when no MCP endpoint is configured.
    mcp_port: int = 3000

    # Startup fetches agent-config.json from this URL and writes it to
    # config.json under `agent_root`, together with the prompt bodies in
    # `prompts/` beside it. An empty value leaves config.json as it is.
    config_url: str = ""

    # Startup reads branding.json and its images from the config bucket at
    # this base URL. When it is empty, the UI keeps its default branding.
    brand_config_url: _NoTrailingSlashStr = ""

    # The branding endpoints publish this deployment identifier alongside the
    # branding.
    instance_id: str = ""

    # Prompts render the current date and time in this IANA zone. An unknown
    # zone falls back to UTC.
    timezone: str = "UTC"

    # A short `gemini_api_key_secret` name resolves against this project.
    google_cloud_project: str = ""

    # This Secret Manager secret, named in full or by a short secret ID, holds
    # the Gemini API key. When it is unset or yields no key, `gemini.api_key`
    # in config.json applies.
    gemini_api_key_secret: str = ""

    # When true, session logs also go to files, in `logs` under `agent_root`.
    #
    # Every Cloud Run instance has its own ephemeral disk, so a session log
    # written to a file dies with the instance and cannot be read across the
    # fleet -- exactly when scaling out makes it most needed. Emitting one JSON
    # object per line on stdout gets the same information into Cloud Logging
    # as structured entries, queryable by session_id and event_type, with no
    # dependency and no credentials.
    #
    # Files are still written off Cloud Run, because tailing one is the fastest
    # way to debug locally. SESSION_LOG_TO_FILE forces either behavior
    # explicitly.
    session_log_to_file: Annotated[
        bool, BeforeValidator(_parse_session_log_to_file)
    ] = Field(default_factory=_default_session_log_to_file)

    @model_validator(mode="before")
    @classmethod
    def _drop_blank_values(cls, data: Any) -> Any:
        """Returns `data` without its empty and whitespace-only strings.

        A variable dropped here counts as unset, so its field takes the default.
        """
        if not isinstance(data, dict):
            return data
        return {
            name: value
            for name, value in data.items()
            if not (isinstance(value, str) and not value.strip())
        }

    @model_validator(mode="after")
    def _keep_agent_root_out_of_static_root(self) -> Settings:
        """Rejects a `static_root` that equals or contains `agent_root`.

        Every file under `static_root` is served to the browser. A
        `static_root` that is `agent_root` or one of its ancestors would
        publish config.json, which can hold the Gemini API key.

        Raises:
            ValueError: `static_root` equals or contains `agent_root`.
        """
        if self.agent_root.resolve().is_relative_to(self.static_root.resolve()):
            raise ValueError(
                f"STATIC_ROOT ({self.static_root}) must not be AGENT_ROOT "
                f"({self.agent_root}) or a directory that contains it: every "
                "file under STATIC_ROOT is served, including config.json."
            )
        return self


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns the settings, read from the environment on the first call.

    Later calls return the same instance; `get_settings.cache_clear()` makes
    the next call read the environment again.

    Raises:
        pydantic.ValidationError: A variable does not parse as its field's
            type, such as a non-numeric AGENT_PORT.
    """
    return Settings()
