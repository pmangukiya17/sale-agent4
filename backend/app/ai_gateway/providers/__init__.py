"""
Concrete Provider Clients - M7.2. The ONLY package in this codebase
permitted to import a real AI provider SDK (anthropic/openai/
google.genai) - see registry.py's own docstring for the grep rule this
convention is meant to make enforceable. Everything in here translates
between the Gateway's own opaque GatewayRequest/GatewayResponse contract
(app.ai_gateway.request) and one specific provider's real SDK shape,
normalizing every SDK-specific exception into app.ai_gateway.errors'
small vocabulary before it ever leaves this package.
"""
