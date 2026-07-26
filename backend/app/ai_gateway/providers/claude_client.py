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
from app.ai_gateway.providers.base import ProviderClient
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

    def is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    @property
    def default_model(self) -> str | None:
        return settings.ANTHROPIC_DEFAULT_MODEL

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        if not self.is_configured():
            raise ProviderAuthError("ANTHROPIC_API_KEY is not configured", provider_key=self.key)

        model = request.model or self.default_model
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
            api_key=settings.ANTHROPIC_API_KEY, timeout=request.timeout_seconds or settings.AI_GATEWAY_DEFAULT_TIMEOUT_SECONDS
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
