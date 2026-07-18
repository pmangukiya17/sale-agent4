"""
ReplyClassifier registry. Same plugin-registry pattern as every other one
in this codebase (app/delivery/credentials/registry.py,
app/delivery/providers/registry.py, app/discovery/providers/registry.py,
app/research/providers/registry.py) - selected by app-level setting
(REPLY_CLASSIFIER_BACKEND, default "rules"), never per-conversation.
Adding an OpenAI/Claude/Gemini/local-model classifier later is a new
class here + one dict entry + changing REPLY_CLASSIFIER_BACKEND - never a
change to reply_intelligence_worker.py, which only ever calls
get_reply_classifier().
"""
from app.core.config import settings
from app.reply_intelligence.classifiers.base import ReplyClassifier
from app.reply_intelligence.classifiers.rules_classifier import RulesReplyClassifier

REPLY_CLASSIFIER_REGISTRY: dict[str, type[ReplyClassifier]] = {
    RulesReplyClassifier.backend_key: RulesReplyClassifier,
}


def get_reply_classifier() -> ReplyClassifier:
    backend_key = settings.REPLY_CLASSIFIER_BACKEND
    classifier_cls = REPLY_CLASSIFIER_REGISTRY.get(backend_key)
    if classifier_cls is None:
        raise KeyError(f"Unknown reply classifier backend '{backend_key}'. Registered: {list(REPLY_CLASSIFIER_REGISTRY)}")
    return classifier_cls()
