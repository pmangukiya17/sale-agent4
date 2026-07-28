"""
Gemini provider clients - M7.2, split M-AIGW-3 (Provider-Neutral AI Gateway,
Gemini Free-Tier Split - see docs/architecture/provider-neutral-ai-gateway-plan.md
Section 7). Translates GatewayRequest/GatewayResponse (app.ai_gateway.request)
to/from the real Gemini API via Google's `google-genai` SDK (requirements.txt -
see that file's own M7.2 comment; this is the current unified SDK, NOT the
older, now-superseded `google-generativeai` package - confirmed via web
search at implementation time, since this SDK is newer and churns faster
than Anthropic's/OpenAI's). One of exactly three files in this codebase
permitted to `import google.genai` - see registry.py's own docstring for
the grep rule this is meant to make enforceable.

M-AIGW-3: this file now defines TWO concrete, registered provider_keys -
`GeminiProviderClient` (key="gemini", PREMIUM tier, unchanged settings/
behavior from before this split) and `GeminiAIStudioProviderClient`
(key="gemini_ai_studio", FREE tier, new). Both share
`_GeminiProviderClientBase` below (the entire translation logic this file
already had) - exactly the same "thin subclass, shared base, distinct
config/tier" shape already established for
OpenAICompatibleProviderClient -> LocalOllamaProviderClient/GroqProviderClient
(see that base class's own docstring for the identical reasoning). Sharing
is deliberate, not incidental: these are the SAME underlying SDK
integration, genuinely differing only in which API key/model settings each
reads and which tier an operator classifies it under - duplicating the
~100 lines of request/response translation logic per key would be a real,
avoidable maintenance burden with zero benefit, and `tiers.py`'s own
docstring is explicit that tier is a deployment/reservation decision, not
a property of the class. `_GeminiProviderClientBase` is intentionally
NOT registered itself (mirrors OpenAICompatibleProviderClient's identical
"not registered itself" convention) and stays private to this module
(leading underscore) since, unlike the OpenAI-compatible base, nothing
outside this file needs to subclass it.

Confidence note, disclosed honestly rather than glossed over: the exact
shape of this SDK's exception hierarchy (ClientError/ServerError with a
`.code` attribute for the HTTP status) is based on the SDK's documented
design, not a live-verified call - this project has no path to a real
Gemini API key/live call to confirm it (same disclosed limitation as
every other external-API integration here). The broad
`except Exception` fallback below, mapped to ProviderUnavailableError,
exists specifically as a safety net for this one client - it is NOT
present in claude_client.py/openai_client.py, whose exception
hierarchies are longer-established and more confidently known. If a real
integration run against this client surfaces an exception type this file
doesn't yet catch specifically, tightening this mapping is expected,
routine follow-up work, not a sign of a design flaw.

Gemini-specific translation notes:
  - Like Claude, system instructions are a separate `config.system_instruction`
    parameter, not a role inside `contents` - _split_system_messages()
    below extracts them the same way claude_client.py does.
  - The assistant role is spelled "model", not "assistant" - translated
    in _to_gemini_contents() below.
"""
import json
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.ai_gateway.accounting import build_usage
from app.ai_gateway.capabilities import ProviderCapabilities
from app.ai_gateway.errors import (
    InvalidRequestError,
    InvalidResponseError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai_gateway.provider_config import resolve_provider_config
from app.ai_gateway.providers.base import ProviderClient
from app.ai_gateway.request import GatewayRequest, GatewayResponse, ResponseFormatType, ToolCall
from app.core.config import settings

_PREMIUM_PROVIDER_KEY = "gemini"
_AI_STUDIO_PROVIDER_KEY = "gemini_ai_studio"

# Protocol-level facts about this SDK integration - see claude_client.py's
# own comment for why streaming=False regardless of the SDK's real support.
# Shared by BOTH provider_keys below unchanged - capability is a fact
# about the wire integration (same SDK, same API surface either way),
# never about which tier an operator classifies a given key under (see
# tiers.py's own docstring). If a future model-specific difference is ever
# found between what an AI Studio key vs. a paid key can do, that's a
# (provider_key, model) capability override (app.ai_gateway.capabilities'
# own docstring), not a reason to fork this declaration.
_CAPABILITIES = ProviderCapabilities(
    structured_output=True,
    tool_calling=True,
    streaming=False,
    vision=True,
    embeddings=False,
    reasoning_support=True,
)

_ROLE_TRANSLATION = {"assistant": "model", "user": "user"}


def _split_system_messages(messages: list[dict]) -> tuple[str | None, list[dict]]:
    system_parts = [m["content"] for m in messages if m.get("role") == "system" and m.get("content")]
    remaining = [m for m in messages if m.get("role") != "system"]
    system = "\n\n".join(system_parts) if system_parts else None
    return system, remaining


def _to_gemini_contents(messages: list[dict]) -> list[genai_types.Content]:
    contents = []
    for message in messages:
        role = _ROLE_TRANSLATION.get(message.get("role"), "user")
        contents.append(genai_types.Content(role=role, parts=[genai_types.Part(text=message.get("content") or "")]))
    return contents


class _GeminiProviderClientBase(ProviderClient):
    """Not registered itself - PROVIDER_CLIENT_REGISTRY only ever holds the
    two concrete subclasses below, exactly like ProviderClient itself and
    OpenAICompatibleProviderClient are never registered directly. Every
    line of request/response translation this file has ever had lives
    here, unchanged by the M-AIGW-3 split - only `api_key`/`default_model`
    (and therefore `is_configured()`, trivially) differ per subclass."""

    capabilities = _CAPABILITIES

    @property
    def _fallback_api_key(self) -> str | None:
        raise NotImplementedError

    @property
    def _fallback_default_model(self) -> str | None:
        raise NotImplementedError

    def _resolved_config(self):
        """M8.3 Step 1 - see claude_client.py's identical helper for the
        full rationale. Each subclass supplies its own settings-derived
        fallback (`_fallback_api_key`/`_fallback_default_model`) since
        `gemini`/`gemini_ai_studio` read entirely distinct settings
        attributes despite sharing this base class - see module docstring."""
        return resolve_provider_config(
            self.key,
            fallback_api_key=self._fallback_api_key,
            fallback_default_model=self._fallback_default_model,
        )

    @property
    def api_key(self) -> str | None:
        return self._resolved_config().api_key

    @property
    def default_model(self) -> str | None:
        return self._resolved_config().default_model

    def is_configured(self) -> bool:
        config = self._resolved_config()
        return config.enabled and bool(config.api_key)

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        config = self._resolved_config()
        if not config.enabled:
            raise ProviderAuthError(f"{self.key} is disabled in AI Gateway provider configuration", provider_key=self.key)
        if not config.api_key:
            raise ProviderAuthError(f"{self.key}'s API key is not configured", provider_key=self.key)

        model = request.model or config.default_model
        if not model:
            raise InvalidRequestError(f"No model specified and no default model is configured for '{self.key}'", provider_key=self.key)

        system, messages = _split_system_messages(request.messages)
        contents = _to_gemini_contents(messages)

        config_kwargs: dict = {}
        if system is not None:
            config_kwargs["system_instruction"] = system
        if request.max_tokens is not None:
            config_kwargs["max_output_tokens"] = request.max_tokens
        if request.temperature is not None:
            config_kwargs["temperature"] = request.temperature
        if request.timeout_seconds:
            config_kwargs["http_options"] = genai_types.HttpOptions(timeout=int(request.timeout_seconds * 1000))
        if request.response_format and request.response_format.type == ResponseFormatType.JSON:
            config_kwargs["response_mime_type"] = "application/json"
            if request.response_format.json_schema:
                config_kwargs["response_schema"] = request.response_format.json_schema
        if request.tools:
            config_kwargs["tools"] = [
                genai_types.Tool(
                    function_declarations=[
                        genai_types.FunctionDeclaration(name=t.name, description=t.description, parameters=t.parameters_json_schema)
                        for t in request.tools
                    ]
                )
            ]

        client = genai.Client(api_key=config.api_key)

        started_at = time.monotonic()
        try:
            response = client.models.generate_content(
                model=model, contents=contents, config=genai_types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
            )
        except genai_errors.ClientError as exc:
            status = getattr(exc, "code", None)
            if status == 401 or status == 403:
                raise ProviderAuthError(str(exc), provider_key=self.key) from exc
            if status == 429:
                raise ProviderRateLimitError(str(exc), provider_key=self.key) from exc
            if status == 400:
                raise InvalidRequestError(str(exc), provider_key=self.key) from exc
            raise ProviderUnavailableError(str(exc), provider_key=self.key) from exc
        except genai_errors.ServerError as exc:
            raise ProviderUnavailableError(str(exc), provider_key=self.key) from exc
        except TimeoutError as exc:
            raise ProviderTimeoutError(str(exc), provider_key=self.key) from exc
        except Exception as exc:  # noqa: BLE001 - safety net for this SDK specifically, see module docstring
            raise ProviderUnavailableError(str(exc), provider_key=self.key) from exc

        if request.timeout_seconds and (time.monotonic() - started_at) > request.timeout_seconds:
            raise ProviderTimeoutError(f"{self.key} response exceeded the requested timeout", provider_key=self.key)

        tool_calls = None
        function_calls = getattr(response, "function_calls", None)
        if function_calls:
            tool_calls = [
                ToolCall(id=f"{self.key}-tool-{i}", name=call.name, arguments=dict(call.args or {}))
                for i, call in enumerate(function_calls)
            ]

        content: str | dict = response.text or ""
        if request.response_format and request.response_format.type == ResponseFormatType.JSON:
            try:
                content = json.loads(content)
            except json.JSONDecodeError as exc:
                raise InvalidResponseError(f"{self.key} did not return valid JSON: {exc}", provider_key=self.key) from exc

        usage_metadata = response.usage_metadata
        usage = build_usage(
            provider_key=self.key,
            model=model,
            prompt_tokens=usage_metadata.prompt_token_count or 0,
            completion_tokens=usage_metadata.candidates_token_count or 0,
        )

        finish_reason = "unknown"
        if response.candidates:
            finish_reason = str(response.candidates[0].finish_reason or "unknown")

        return GatewayResponse(
            content=content, tool_calls=tool_calls, usage=usage, provider_key=self.key, model=model, finish_reason=finish_reason
        )


class GeminiProviderClient(_GeminiProviderClientBase):
    """Unchanged provider_key/settings/behavior from before the M-AIGW-3
    split - a deployment already using `GOOGLE_API_KEY`/`GOOGLE_DEFAULT_MODEL`
    for a paid Gemini key is completely unaffected. Stays PREMIUM tier (see
    tiers.py) - a paid key genuinely is a premium-tier cost, same
    classification as before this split existed."""

    key = _PREMIUM_PROVIDER_KEY

    @property
    def _fallback_api_key(self) -> str | None:
        return settings.GOOGLE_API_KEY

    @property
    def _fallback_default_model(self) -> str | None:
        return settings.GOOGLE_DEFAULT_MODEL


class GeminiAIStudioProviderClient(_GeminiProviderClientBase):
    """M-AIGW-3 addition. Gemini AI Studio's free-tier key - a distinct
    provider_key/settings pair from the paid `gemini` key above, tiered
    FREE (see tiers.py.PROVIDER_TIER_REGISTRY) so it's auto-attempted
    (never gated behind premium approval) whenever configured. Unset by
    default (`GOOGLE_AI_STUDIO_API_KEY`/`GOOGLE_AI_STUDIO_DEFAULT_MODEL` -
    see app.core.config.settings' own comment) - zero effect on any
    deployment until an operator deliberately obtains and sets an AI
    Studio key."""

    key = _AI_STUDIO_PROVIDER_KEY

    @property
    def _fallback_api_key(self) -> str | None:
        return settings.GOOGLE_AI_STUDIO_API_KEY

    @property
    def _fallback_default_model(self) -> str | None:
        return settings.GOOGLE_AI_STUDIO_DEFAULT_MODEL
