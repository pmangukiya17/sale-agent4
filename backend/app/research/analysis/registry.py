"""
AIAnalysisEngine registry - M2 Phase 3. Same plugin-registry pattern as
every other one in this codebase (app/delivery/credentials/registry.py,
app/delivery/providers/registry.py, app/discovery/providers/registry.py,
app/research/providers/registry.py, and most directly,
app/reply_intelligence/classifiers/registry.py) - selected by an
app-level setting (RESEARCH_ANALYSIS_ENGINE_BACKEND), never
per-research-job. Adding a future analysis backend later is a new class
here + one dict entry + changing RESEARCH_ANALYSIS_ENGINE_BACKEND - never
a change to run_research_request() (app/research/pipeline.py), which
only ever calls get_analysis_engine().

Before this file existed, pipeline.py constructed
DeterministicAnalysisEngine() directly at its one call site - this
registry replaces that direct construction with a selectable one.
Default was "deterministic" for the initial Phase 3 commit (byte-for-
byte unchanged behavior until an operator explicitly opted in to "llm");
per that commit's own rollout plan step 4, the default has since been
flipped to "llm" in a separate, explicitly CEO-approved follow-up
commit - "deterministic" remains fully selectable (config-only, no code
change) for anyone who wants the original keyword/regex engine back.
"""
from app.core.config import settings
from app.research.analysis.base import AIAnalysisEngine
from app.research.analysis.deterministic_stub import DeterministicAnalysisEngine
from app.research.analysis.llm_engine import LLMAnalysisEngine

ANALYSIS_ENGINE_REGISTRY: dict[str, type[AIAnalysisEngine]] = {
    "deterministic": DeterministicAnalysisEngine,
    "llm": LLMAnalysisEngine,
}


def get_analysis_engine() -> AIAnalysisEngine:
    backend_key = settings.RESEARCH_ANALYSIS_ENGINE_BACKEND
    engine_cls = ANALYSIS_ENGINE_REGISTRY.get(backend_key)
    if engine_cls is None:
        raise KeyError(f"Unknown research analysis engine backend '{backend_key}'. Registered: {list(ANALYSIS_ENGINE_REGISTRY)}")
    return engine_cls()
