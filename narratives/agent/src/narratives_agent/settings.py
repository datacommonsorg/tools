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
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# Boolean environment variables (such as `GOOGLE_GENAI_USE_VERTEXAI`) turn on
# with one of these values, compared after stripping and lowercasing, and off
# with any other value.
_TRUTHY_ENV_VALUES = ("1", "true", "yes")

# `MIN_SECRET_BYTES` is the shortest `TRANSCRIPT_HMAC_SECRET` accepted: the
# 256 bits of an HMAC-SHA256 key.
MIN_SECRET_BYTES = 32

# Environment variable names for credentials and Secret Manager references.
GEMINI_API_KEY_SECRET_ENV = "GEMINI_API_KEY_SECRET"
DC_API_KEY_ENV = "DC_API_KEY"
DC_API_KEY_SECRET_ENV = "DC_API_KEY_SECRET"
TRANSCRIPT_HMAC_SECRET_ENV = "TRANSCRIPT_HMAC_SECRET"
TRANSCRIPT_HMAC_SECRET_NAME_ENV = "TRANSCRIPT_HMAC_SECRET_NAME"


def validate_hmac_secret(
    secret: str, source: str = TRANSCRIPT_HMAC_SECRET_ENV
) -> str:
    """Rejects an HMAC secret shorter than `MIN_SECRET_BYTES`.

    Args:
        secret: The raw secret string to validate.
        source: The name of the environment variable or configuration source,
            used in error messages.

    Returns:
        The validated secret string.

    Raises:
        ValueError: The secret is shorter than `MIN_SECRET_BYTES`.
    """
    if len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise ValueError(
            f"{source} must be at least {MIN_SECRET_BYTES} bytes; "
            "generate one with `openssl rand -hex 32`."
        )
    return secret


def _normalize_url_path_prefix(value: str) -> str:
    """Normalizes `value` to a leading-slash path without trailing slashes."""
    stripped = value.strip("/")
    return f"/{stripped}" if stripped else ""


def _is_truthy_env_value(value: bool | str) -> bool:
    """Returns whether `value` is one of `_TRUTHY_ENV_VALUES`.

    Args:
        value: The raw environment string, or the bool the field's default or
            default factory produced, which is validated like any input.

    Returns:
        A bool `value` unchanged; otherwise whether the stripped, lowercased
        string is one of `_TRUTHY_ENV_VALUES`.
    """
    if isinstance(value, bool):
        return value
    return value.strip().lower() in _TRUTHY_ENV_VALUES


def _default_static_root(data: dict[str, Any]) -> Path:
    """Returns the `static` directory under the validated `agent_root`."""
    agent_root: Path = data["agent_root"]
    return agent_root / "static"


def _default_defaults_dir(data: dict[str, Any]) -> Path:
    """Returns `agent_root / "defaults"` if it exists, or `../defaults`."""
    agent_root: Path = data["agent_root"]
    staged = agent_root / "defaults"
    if staged.is_dir():
        return staged
    return agent_root.parent / "defaults"


# URL path prefixes are normalized to start with a single "/" and have no
# trailing slashes, so they join with "/<path>" without doubling the separator.
_UrlPathPrefixStr = Annotated[str, AfterValidator(_normalize_url_path_prefix)]
_EnvBool = Annotated[bool, BeforeValidator(_is_truthy_env_value)]


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

    # The `prompts/` directory under this path holds the default prompt bodies,
    # which are the base layer of the prompt slots on every configuration path.
    # When `config_url` is unset and `agent_root/config.json` is absent,
    # `agent-config.json` is read from here as well.
    defaults_dir: Path = Field(default_factory=_default_defaults_dir)

    # The local development server (`uv run narratives-agent-dev`) listens on
    # this port.
    agent_port: int = 5001

    # The URL subpath under which the application (API, healthz, and SPA) is
    # served when mounted behind a path-routing load balancer (e.g.
    # "/narratives"); "/" or empty serves at the root.
    base_path: _UrlPathPrefixStr = ""

    # The agent API routers are mounted under this URL path prefix; "/" mounts
    # them at the root because trailing slashes are stripped.
    agent_api_prefix: _UrlPathPrefixStr = "/agent"

    # CORS allows the comma-separated origins listed here. Left unset, it
    # allows only the local development origins, and none at all on Cloud Run.
    allowed_origin: str = ""

    # Cloud Run sets this to the name of the service. It is empty anywhere
    # else, such as on a developer machine.
    k_service: str = ""

    # Kubernetes sets this to the cluster API server host in every pod. It is
    # empty outside Kubernetes.
    kubernetes_service_host: str = ""

    # "off", compared case-insensitively, stops credentials from being attached
    # to MCP requests; any other value, like the default "auto", chooses them by
    # target host.
    data_plane_auth: str = "auto"

    # The agent sends this API key as `X-API-Key` to public Data Commons hosts.
    dc_api_key: str = ""

    # This Secret Manager secret, named in full or by a short secret ID, holds
    # the Data Commons API key. When `dc_api_key` is unset, this is resolved
    # against Secret Manager at startup.
    dc_api_key_secret: str = ""

    # The agent reaches the MCP server at this URL, which takes precedence over
    # `mcp.server_url` in config.json. With neither set, it calls localhost on
    # `mcp_port`.
    mcp_server_url: str = ""

    # The co-located MCP server listens on this port, which the agent calls
    # when no MCP endpoint is configured.
    mcp_port: int = 3000

    # Startup fetches `agent-config.json` and its sibling `prompts/` from this
    # GCS URL and caches the merged configuration in memory.
    config_url: str = ""

    # Prompts render the current date and time in this IANA zone. An unknown
    # zone falls back to UTC.
    timezone: str = "UTC"

    # Short secret names in `gemini_api_key_secret`, `dc_api_key_secret`, and
    # `transcript_hmac_secret_name` resolve against this project, and Vertex AI
    # calls run against it when `google_genai_use_vertexai` is true.
    google_cloud_project: str = ""

    # Region for Vertex AI Gemini calls when `google_genai_use_vertexai` is
    # true.
    google_cloud_location: str = "us-central1"

    # When true, Gemini calls authenticate with Application Default Credentials
    # against Vertex AI instead of using a Gemini API key.
    google_genai_use_vertexai: _EnvBool = False

    # When false, `/agent/chat/stream` aborts every turn with reason
    # `chat_disabled` before making any Gemini or MCP calls.
    # Acts as an application-level emergency off switch.
    enable_chat: _EnvBool = True

    # This Secret Manager secret, named in full or by a short secret ID, holds
    # the Gemini API key. When it is unset or yields no key, `gemini.api_key`
    # in config.json applies.
    gemini_api_key_secret: str = ""

    # Transcript turns are signed with HMAC-SHA256 under this secret, so a
    # turn signed by one instance verifies on any other. It is required on
    # Kubernetes; when it is unset elsewhere, each process signs with a random
    # key of its own, and a transcript then verifies only on the process that
    # signed it. `SecretStr` keeps the value out of `repr()` output and logs.
    transcript_hmac_secret: SecretStr = SecretStr("")

    # This Secret Manager secret, named in full or by a short secret ID, holds
    # the 32+ byte HMAC-SHA256 signing key. When `transcript_hmac_secret` is
    # unset, this is resolved against Secret Manager at startup.
    transcript_hmac_secret_name: str = ""

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

    @field_validator("transcript_hmac_secret")
    @classmethod
    def _require_a_strong_secret(cls, value: SecretStr) -> SecretStr:
        """Rejects a transcript secret shorter than `MIN_SECRET_BYTES`.

        A short secret can be guessed offline from any signed turn, which
        would let a client forge its own transcript. Unset is allowed, in
        which case each process generates its own key.

        Raises:
            ValueError: The secret is set and shorter than the minimum.
        """
        secret = value.get_secret_value()
        if secret:
            validate_hmac_secret(secret, TRANSCRIPT_HMAC_SECRET_ENV)
        return value

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
