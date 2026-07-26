"""
OpenAICompatibleProviderClient - M11 (AI Provider Hierarchy). A GENERIC base
class for any provider that speaks the OpenAI chat-completions wire format
against a configurable base_url - which today means Ollama (and vLLM, LM
Studio, text-generation-webui - any local server, not just Ollama
specifically) for Local, and Groq for Free. Reuses the `openai` SDK itself
(already a pinned dependency - requirements.txt - for OpenAIProviderClient)
pointed at a different base_url, rather than adding a new third-party
dependency or hand-rolling HTTP calls. This is ~90% the same translation
logic as app.ai_gateway.providers.openai_client.OpenAIProviderClient,
factored out here so that file is untouched and this one has exactly one
job: know WHERE to point the SDK and WHICH settings to read, via three
abstract properties subclasses implement (base_url, api_key, default_model,
provider_display_name is cosmetic-only for error messages).

Concrete subclasses: local_client.LocalOllamaProviderClient,
groq_client.GroqProviderClient. Both are otherwise-empty subclasses - see
those files' own (short) docstrings for why there's deliberately no
provider-specific logic in either.

is_configured() differs from OpenAIProviderClient's own: an API key is
NOT required (most local inference servers accept none) - only a base_url
is. A subclass whose provider genuinely requires a key (Groq) enforces
that in its own is_configured() override instead.
"""
import json
import time

import openai

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

# Shared protocol-level default for every OpenAI-compatible subclass
# (LocalOllamaProviderClient, GroqProviderClient) - best-effort
# structured_output/tool_calling per this file's own disclosed caveat
# ("not every local model/server actually honors response_format the way
# OpenAI's own API does"), streaming=False (see claude_client.py's own
# comment - AIGateway.stream() itself is unimplemented regardless of
# provider), reasoning_support=False as the conservative default for a
# generic local/free model (a specific model known to reason well is a
# per-(provider, model) capability override, not a class-level change -
# see app.ai_gateway.capabilities' own docstring).
_CAPABILITIES = ProviderCapabilities(
    structured_output=True,
    tool_calling=True,
    streaming=False,
    vision=False,
    embeddings=False,
    reasoning_support=False,
)


class OpenAICompatibleProviderClient(ProviderClient):
    """Not registered itself - PROVIDER_CLIENT_REGISTRY only ever holds
    concrete subclasses, exactly like ProviderClient itself is never
    registered directly."""

    capabilities = _CAPABILITIES

    @property
    def base_url(self) -> str | None:
        raise NotImplementedError

    @property
    def api_key(self) -> str | None:
        raise NotImplementedError

    @property
    def default_model(self) -> str | None:
        raise NotImplementedError

    def is_configured(self) -> bool:
        return bool(self.base_url)

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        if not self.is_configured():
            raise ProviderAuthError(f"{self.key}'s base_url is not configured", provider_key=self.key)

        model = request.model or self.default_model
        if not model:
            raise InvalidRequestError(f"No model specified and no default model is configured for '{self.key}'", provider_key=self.key)

        client = openai.OpenAI(
            base_url=self.base_url,
            # Most local servers ignore this entirely; the SDK still
            # requires a non-empty string to construct the client.
            api_key=self.api_key or "not-required",
            timeout=request.timeout_seconds or settings.AI_GATEWAY_DEFAULT_TIMEOUT_SECONDS,
        )

        kwargs: dict = {"model": model, "messages": request.messages}
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.response_format and request.response_format.type == ResponseFormatType.JSON:
            # Not every local model/server actually honors response_format
            # the way OpenAI's own API does - a model that ignores this and
            # returns non-JSON text is caught below by the same
            # InvalidResponseError parse-failure path OpenAIProviderClient
            # itself uses; this is disclosed, not silently assumed to work.
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
            # The most common real-world failure for a local provider - the
            # server (Ollama etc.) simply isn't running - lands here, and
            # is fallback_eligible (see errors.py), so the chain correctly
            # moves on to the next tier rather than hard-failing.
            raise ProviderUnavailableError(str(exc), provider_key=self.key) from exc
        except openai.BadRequestError as exc:
            raise InvalidRequestError(str(exc), provider_key=self.key) from exc
        except openai.APIStatusError as exc:  # noqa: BLE001 - catch-all for any status-coded error this SDK adds later
            raise ProviderUnavailableError(str(exc), provider_key=self.key) from exc

        if request.timeout_seconds and (time.monotonic() - started_at) > request.timeout_seconds:
            raise ProviderTimeoutError(f"{self.key} response exceeded the requested timeout", provider_key=self.key)

        message = response.choices[0].message
        tool_calls = None
        if message.tool_calls:
            tool_calls = []
            for call in message.tool_calls:
                try:
                    arguments = json.loads(call.function.arguments) if call.function.arguments else {}
                except json.JSONDecodeError as exc:
                    raise InvalidResponseError(f"{self.key} tool call arguments were not valid JSON: {exc}", provider_key=self.key) from exc
                tool_calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))

        content: str | dict = message.content or ""
        if request.response_format and request.response_format.type == ResponseFormatType.JSON:
            try:
                content = json.loads(content)
            except json.JSONDecodeError as exc:
                raise InvalidResponseError(f"{self.key} did not return valid JSON: {exc}", provider_key=self.key) from exc

        usage = build_usage(
            provider_key=self.key,
            model=model,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )

        return GatewayResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            provider_key=self.key,
            model=model,
            finish_reason=response.choices[0].finish_reason or "unknown",
        )
