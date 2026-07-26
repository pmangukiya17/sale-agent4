"""
llm_mapping.py - M-AIGW-5 (Outreach as the Gateway's second production
consumer - see docs/architecture/provider-neutral-ai-gateway-plan.md
Section 12). Pure, stdlib-only helpers shared between OutreachEmailAgent
(llm_agent.py, which must stay importable without sqlalchemy) and
LLMEmailChannelProvider (llm_email_provider.py, which already requires
sqlalchemy via OutreachContext - same as EmailChannelProvider does
today). Deliberately its own small module, NOT shared with
app.research.analysis.llm_mapping - each domain owns its own pure mapping
module (Research's own llm_mapping.py isn't shared with Discovery's
brave_search_mapping.py either), even though the two parsing functions
below are structurally similar.

Expected model response shape - ONE JSON object per email-generation
call:

{
  "subject": str,
  "blocks": [{"block_key": str, "content": str, "reasoning": str|null}, ...],
  "confidence": float|null,
  "reasoning": str|null
}

`blocks` covers only the AI_ASSISTED/AI_GENERATED blocks the Agent was
asked to write - FIXED blocks are never sent to the model and never
appear here (see llm_email_provider.py's own docstring for why).
"""
import json
from typing import Any

REQUIRED_TOP_LEVEL_KEYS = ("subject", "blocks")


def parse_agent_response_content(content: Any) -> dict:
    """`content` is GatewayResponse.content (str | dict). Returns a plain
    dict or raises ValueError - never anything else, so callers can treat
    ValueError uniformly as "malformed response, worth a retry.". Mirrors
    app.research.analysis.llm_mapping.parse_agent_response_content
    exactly (same generic str/dict handling), duplicated per this
    module's own docstring."""
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"response content is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("response content did not decode to a JSON object")
        return parsed
    raise ValueError(f"unexpected response content type: {type(content).__name__}")


def validate_email_response(parsed: dict) -> None:
    """Raises ValueError describing exactly what's missing/malformed -
    never silently accepts a partial response. Both this and
    parse_agent_response_content are called from
    OutreachEmailAgent.interpret(); either raising ValueError there is
    mapped to AgentOutcome.RETRY."""
    missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in parsed]
    if missing:
        raise ValueError(f"response is missing required key(s): {missing}")
    if not isinstance(parsed["subject"], str) or not parsed["subject"].strip():
        raise ValueError("response 'subject' must be a non-empty string")
    if not isinstance(parsed["blocks"], list):
        raise ValueError("response 'blocks' must be a JSON array")
    for i, block in enumerate(parsed["blocks"]):
        if not isinstance(block, dict):
            raise ValueError(f"blocks[{i}] must be a JSON object")
        if "block_key" not in block or not isinstance(block["block_key"], str):
            raise ValueError(f"blocks[{i}] is missing a string 'block_key'")
        if "content" not in block or not isinstance(block["content"], str):
            raise ValueError(f"blocks[{i}] (block_key={block.get('block_key')!r}) is missing a string 'content'")


def index_blocks_by_key(parsed: dict) -> dict[str, dict]:
    """Returns {block_key: block_dict} for O(1) lookup while assembling
    the final email in playbook block order - the model's own response
    order is not assumed to match the playbook's order."""
    return {block["block_key"]: block for block in parsed.get("blocks", []) if isinstance(block, dict) and "block_key" in block}
