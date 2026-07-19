"""
Prompt Builder - M7.2, added per the user's post-architecture-review
refinement #1. Sits between the AI Agent Runtime and the AI Gateway:

    Workflow Action -> AI Agent Runtime -> Prompt Builder -> AI Gateway -> Provider Router

Its one job: turn a PromptContext (business content an Agent contributed
via Agent.build_context()) plus an ExecutionPolicy (provider/model/
temperature/etc., resolved by AgentRuntime - never by the Agent or by
this package) into a GatewayRequest. Nothing else. It never calls the
Gateway itself (AgentRuntime.run() does that, after calling
PromptBuilder.build()) and it never knows about any specific Agent - see
builder.py's own docstring for why it takes a plain PromptContext rather
than an Agent instance.
"""
