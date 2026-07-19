"""
OpenAIProviderClient - M7.2. Translates GatewayRequest/GatewayResponse
(app.ai_gateway.request) to/from the real OpenAI Chat Completions API via
the `openai` SDK (requirements.txt - see that file's own M7.2 comment
for the exact pinned version). One of exactly three files in this
codebase permitted to `import openai` - see registry.py's own docstring
for the grep rule this is meant to make enforceable.

Unlike Claude, OpenAI's `messages` shape already matches
GatewayRequest.messages directly (role/content, system role included
inline) - no translation needed there. response_format maps directly
onto this API's own native `response_format={"type": "json_object"}` (or
`{"type": "json_schema", "json_schema": {...}}` when a schema is
supplied) - no prompt-instruction workaround needed here, unlike Claude.
"""
import json
import time

import openai

from app.ai_gateway.accounting import build_usage
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

_PROVIDER_KEY = "openai"


class OpenAIProviderClient(ProviderClient):
    key = _PROVIDER_KEY

    def is_configured(self) -> bool:
        return bool(settings.OPENAI_API_KEY)

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        if not self.is_configured():
            raise ProviderAuthError("OPENAI_API_KEY is not configured", provider_key=self.key)

        model = request.model or settings.OPENAI_DEFAULT_MODEL
        if not model:
            raise InvalidRequestError("No model specified and settings.OPENAI_DEFAULT_MODEL is unset", provider_key=self.key)

        client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY, timeout=request.timeout_seconds or settings.AI_GATEWAY_DEFAULT_TIMEOUT_SECONDS
        )

        kwargs: dict = {"model": model, "messages": request.messages}
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.response_format and request.response_format.type == ResponseFormatType.JSON:
            if request.response_format.json_schema:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "response", "schema": request.response_format.json_schema, "strict": True},
                }
            else:
                kwargs["response_format"] = {"type": "json_object"}
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters_json_schema},
                }
                for t in request.tools
            ]

        started_at = time.monotonic()
        try:
            response = client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise ProviderAuthError(str(exc), provider_key=self.key) from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimitError(str(exc), provider_key=self.key) from exc
        except openai.APITimeoutError as exc:
            raise ProviderTimeoutError(str(exc), provider_key=self.key) from exc
        except (openai.APIConnectionError, openai.InternalServerError) as exc:
            raise ProviderUnavailableError(str(exc), provider_key=self.key) from exc
        except openai.BadRequestError as exc:
            raise InvalidRequestError(str(exc), provider_key=self.key) from exc
        except openai.APIStatusError as exc:  # noqa: BLE001 - catch-all for any status-coded error this SDK adds later
            raise ProviderUnavailableError(str(exc), provider_key=self.key) from exc

        if request.timeout_seconds and (time.monotonic() - started_at) > request.timeout_seconds:
            raise ProviderTimeoutError("OpenAI response exceeded the requested timeout", provider_key=self.key)

        message = response.choices[0].message
        tool_calls = None
        if message.tool_calls:
            tool_calls = []
            for call in message.tool_calls:
                try:
                    arguments = json.loads(call.function.arguments) if call.function.arguments else {}
                except json.JSONDecodeError as exc:
                    raise InvalidResponseError(f"OpenAI tool call arguments were not valid JSON: {exc}", provider_key=self.key) from exc
                tool_calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))

        content: str | dict = message.content or ""
        if request.response_format and request.response_format.type == ResponseFormatType.JSON:
            try:
                content = json.loads(content)
            except json.JSONDecodeError as exc:
                raise InvalidResponseError(f"OpenAI did not return valid JSON: {exc}", provider_key=self.key) from exc

        usage = build_usage(
            provider_key=self.key,
            model=model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )

        return GatewayResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            provider_key=self.key,
            model=model,
            finish_reason=response.choices[0].finish_reason or "unknown",
        )
