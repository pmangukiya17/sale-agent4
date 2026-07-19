"""
AI Gateway - M7.2. Provider abstraction: retries, timeouts, streaming,
JSON mode, tool calling, token/cost accounting, rate limiting, fallback,
error normalization. No business logic lives here - see client.py's own
docstring for the exact boundary.

Structural boundary, enforced from this first module onward, matching
app/workflow_engine/'s own precedent: nothing outside
app/ai_gateway/providers/ may import a concrete provider SDK (anthropic/
openai/google.genai) directly - see providers/registry.py's own
docstring for the grep rule this is meant to make enforceable. Every
other module in this package (and everything above it - AI Agent
Runtime, Prompt Builder, Workflow Actions) talks to providers only
through GatewayRequest/GatewayResponse (request.py) and AIGateway
(client.py) - both entirely provider-agnostic.
"""
