"""
ClaudeProviderClient - M7.2. Translates GatewayRequest/GatewayResponse
(app.ai_gateway.request) to/from the real Anthropic Messages API via the
`anthropic` SDK (requirements.txt - see that file's own M7.2 comment for
the exact pinned version). This is one of exactly three files in this
codebase permitted to `import anthropic` - see registry.py's own
docstring for the grep rule this is meant to make enforceable.

Anthropic-specific translation notes (why this file isn't a trivial
pass-through):
  - The Messages API takes `system` as its OWN top-level parameter, not
    a "system"-role message inside `messages` (unlike OpenAI/Gemini) -
    _split_system_messages() below extracts and concatenates every
    role="system" GatewayRequest message into one system string.
  - No dedicated "JSON mode" flag exists on this API the way OpenAI's
    response_format does - ResponseFormatType.JSON is honored by
    appending an explicit formatting instruction to the system prompt
    and parsing the resulting text as JSON, raising InvalidResponseError
    if that parse fails. A future refinement could instead use tool-use
    forced-schema output for stronger guarantees - noted here as a
    known, deliberate v1 simplification, not implemented in M7.2.
  - Tool calls arrive as "tool_use" content blocks, alongside ordinary
    "text" blocks, in a single `response.content` list - _parse_content()
    below separates the two.
"""
import json
import time

import anthropic

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
from app.ai_gateway.providers.base import ConnectionTestResult, ProviderClient
from app.ai_gateway.request import GatewayRequest, GatewayResponse, ResponseFormatType, ToolCall
from app.core.config import settings

_PROVIDER_KEY = "claude"

# Protocol-level facts about the Messages API integration itself (see
# app.ai_gateway.capabilities' own docstring for why this is provider-level,
# not per-model). structured_output=True reflects the prompt-instruction +
# parse workaround this file already implements (see module docstring) -
# not a native JSON mode, but a real, working capability from this
# Gateway's point of view either way. streaming=False regardless of the
# SDK's real streaming support - AIGateway.stream() itself is unimplemented
# (see client.py) - revisit when it ships. reasoning_support=True is a
# provider-level default (Claude's current lineup generally reasons well);
# a future per-model override can correct this for a specific smaller/older
# model once one is actually configured (see resolve_capabilities()).
_CAPABILITIES = ProviderCapabilities(
    structured_output=True,
    tool_calling=True,
    streaming=False,
    vision=True,
    embeddings=False,
    reasoning_support=True,
)


def _split_system_messages(messages: list[dict]) -> tuple[str | None, list[dict]]:
    system_parts = [m["content"] for m in messages if m.get("role") == "system" and m.get("content")]
    remaining = [m for m in messages if m.get("role") != "system"]
    system = "\n\n".join(system_parts) if system_parts else None
    return system, remaining


def _parse_content(content_blocks: list) -> tuple[str, list[ToolCall] | None]:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in content_blocks:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input or {}))
    return "\n".join(text_parts), (tool_calls or None)


class ClaudeProviderClient(ProviderClient):
    key = _PROVIDER_KEY
    capabilities = _CAPABILITIES

    def _resolved_config(self):
        """M8.3 (AI Gateway Management & Control, Step 1). Every read of
        this provider's effective API key/default model goes through
        `resolve_provider_config()` - a fresh DB read every call (see that
        module's own docstring for why) merged over this file's own
        `settings.ANTHROPIC_*` fallback values, so a deployment that never
        touches the (future) Provider Management UI behaves byte-for-byte
        as it did before this milestone."""
        return resolve_provider_config(
            self.key,
            fallback_api_key=settings.ANTHROPIC_API_KEY,
            fallback_default_model=settings.ANTHROPIC_DEFAULT_MODEL,
        )

    def is_configured(self) -> bool:
        config = self._resolved_config()
        return config.enabled and bool(config.api_key)

    @property
    def default_model(self) -> str | None:
        return self._resolved_config().default_model

    def test_connection(self) -> ConnectionTestResult:
        """M8.3 Step 2 (Provider Management). Uses the Anthropic SDK's
        Models API (`client.models.list()`, GET /v1/models) - a real
        connectivity + authentication check that costs nothing and burns
        no completion tokens, unlike a real Messages call. Confidence
        note, disclosed rather than glossed over (same discipline
        gemini_client.py's own module docstring already established for
        this SDK family): the exact attribute a returned model object
        exposes its id under (`.id` vs `.display_name`) is read
        defensively via `getattr` rather than assumed, since this project
        has no live Anthropic API key to confirm the exact shape against
        a real call."""
        config = self._resolved_config()
        if not config.enabled:
            return ConnectionTestResult(success=False, message=f"{self.key} is disabled in AI Gateway provider configuration")
        if not config.api_key:
            return ConnectionTestResult(success=False, message="ANTHROPIC_API_KEY is not configured")

        client = anthropic.Anthropic(api_key=config.api_key, timeout=10.0)
        started_at = time.monotonic()
        try:
            page = client.models.list(limit=20)
            models = [getattr(m, "id", None) or getattr(m, "display_name", None) or str(m) for m in page]
        except anthropic.AuthenticationError as exc:
            return ConnectionTestResult(success=False, message=f"Authentication failed: {exc}")
        except Exception as exc:  # noqa: BLE001 - a connection test must never raise, only report
            return ConnectionTestResult(success=False, message=str(exc))
        latency_ms = (time.monotonic() - started_at) * 1000
        return ConnectionTestResult(success=True, message="Connected", latency_ms=latency_ms, available_models=models[:50])

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        config = self._resolved_config()
        if not config.enabled:
            raise ProviderAuthError(f"{self.key} is disabled in AI Gateway provider configuration", provider_key=self.key)
        if not config.api_key:
            raise ProviderAuthError("ANTHROPIC_API_KEY is not configured", provider_key=self.key)

        model = request.model or config.default_model
        if not model:
            raise InvalidRequestError(
                "No model specified and settings.ANTHROPIC_DEFAULT_MODEL is unset", provider_key=self.key
            )

        system, messages = _split_system_messages(request.messages)
        if request.response_format and request.response_format.type == ResponseFormatType.JSON:
            instruction = "Respond with valid JSON only, no surrounding prose or markdown fences."
            if request.response_format.json_schema:
                instruction += f" Conform to this JSON schema: {json.dumps(request.response_format.json_schema)}"
            system = f"{system}\n\n{instruction}" if system else instruction

        client = anthropic.Anthropic(
            api_key=config.api_key, timeout=request.timeout_seconds or settings.AI_GATEWAY_DEFAULT_TIMEOUT_SECONDS
        )

        kwargs: dict = {
            "model": model,
            "max_tokens": request.max_tokens or 4096,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters_json_schema} for t in request.tools
            ]

        started_at = time.monotonic()
        try:
            response = client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise ProviderAuthError(str(exc), provider_key=self.key) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimitError(str(exc), provider_key=self.key) from exc
        except anthropic.APITimeoutError as exc:
            raise ProviderTimeoutError(str(exc), provider_key=self.key) from exc
        except (anthropic.APIConnectionError, anthropic.InternalServerError) as exc:
            raise ProviderUnavailableError(str(exc), provider_key=self.key) from exc
        except anthropic.BadRequestError as exc:
            raise InvalidRequestError(str(exc), provider_key=self.key) from exc
        except anthropic.APIStatusError as exc:  # noqa: BLE001 - catch-all for any status-coded error this SDK adds later
            raise ProviderUnavailableError(str(exc), provider_key=self.key) from exc

        if request.timeout_seconds and (time.monotonic() - started_at) > request.timeout_seconds:
            raise ProviderTimeoutError("Claude response exceeded the requested timeout", provider_key=self.key)

        text, tool_calls = _parse_content(response.content)

        content: str | dict = text
        if request.response_format and request.response_format.type == ResponseFormatType.JSON:
            try:
                content = json.loads(text)
            except (json.JSONDecodeError, TypeError) as exc:
                raise InvalidResponseError(f"Claude did not return valid JSON: {exc}", provider_key=self.key) from exc

        usage = build_usage(
            provider_key=self.key,
            model=model,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )

        return GatewayResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            provider_key=self.key,
            model=model,
            finish_reason=response.stop_reason or "unknown",
        )
