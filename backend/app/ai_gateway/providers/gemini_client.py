"""
GeminiProviderClient - M7.2. Translates GatewayRequest/GatewayResponse
(app.ai_gateway.request) to/from the real Gemini API via Google's
`google-genai` SDK (requirements.txt - see that file's own M7.2 comment;
this is the current unified SDK, NOT the older, now-superseded
`google-generativeai` package - confirmed via web search at
implementation time, since this SDK is newer and churns faster than
Anthropic's/OpenAI's). One of exactly three files in this codebase
permitted to `import google.genai` - see registry.py's own docstring for
the grep rule this is meant to make enforceable.

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
from app.ai_gateway.providers.base import ProviderClient
from app.ai_gateway.request import GatewayRequest, GatewayResponse, ResponseFormatType, ToolCall
from app.core.config import settings

_PROVIDER_KEY = "gemini"

# Protocol-level facts about this SDK integration - see claude_client.py's
# own comment for why streaming=False regardless of the SDK's real support.
# This provider_key stays PREMIUM-tier (see tiers.py) - M-AIGW-3 (Gemini
# free-tier split) is separate, deferred, unimplemented work; a future
# `gemini_ai_studio` provider_key would declare the identical capabilities
# below (same underlying client), just a different tier classification.
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


class GeminiProviderClient(ProviderClient):
    key = _PROVIDER_KEY
    capabilities = _CAPABILITIES

    def is_configured(self) -> bool:
        return bool(settings.GOOGLE_API_KEY)

    @property
    def default_model(self) -> str | None:
        return settings.GOOGLE_DEFAULT_MODEL

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        if not self.is_configured():
            raise ProviderAuthError("GOOGLE_API_KEY is not configured", provider_key=self.key)

        model = request.model or self.default_model
        if not model:
            raise InvalidRequestError("No model specified and settings.GOOGLE_DEFAULT_MODEL is unset", provider_key=self.key)

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

        client = genai.Client(api_key=settings.GOOGLE_API_KEY)

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
            raise ProviderTimeoutError("Gemini response exceeded the requested timeout", provider_key=self.key)

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
                raise InvalidResponseError(f"Gemini did not return valid JSON: {exc}", provider_key=self.key) from exc

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
