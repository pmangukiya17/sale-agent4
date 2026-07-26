"""
Tests for app/research/analysis/registry.py (get_analysis_engine()) -
M2 Phase 3. Disclosed as NOT executed in the authoring sandbox: this
module imports app.core.config (pydantic_settings) and
DeterministicAnalysisEngine/LLMAnalysisEngine, both of which pull in
SQLAlchemy ORM models - both confirmed absent here, no PyPI/network
access to install them. py_compile-checked clean here; run for real in
Docker.

Imports app.db.base before any model-touching import, same as every
other DB-backed test in this project - both engine classes returned by
get_analysis_engine() ultimately reach ResearchContext/RawDocument
(SQLAlchemy-mapped), and CompanyProfile's own "Industry" relationship
target (a string, resolved lazily) only resolves if app.models.industry
has actually been imported somewhere in this process before the first
mapper is configured. See test_llm_analysis_engine_e2e.py's own
docstring for the full root-cause explanation.

Run standalone (Docker/full environment only) with:
    python -m unittest tests.test_analysis_engine_registry_e2e
"""
import unittest

from app.db import base as _base  # noqa: F401  (registers every model - see module docstring)
from app.core.config import settings
from app.research.analysis.deterministic_stub import DeterministicAnalysisEngine
from app.research.analysis.llm_engine import LLMAnalysisEngine
from app.research.analysis.registry import get_analysis_engine


class TestAnalysisEngineRegistry(unittest.TestCase):
    def setUp(self):
        self._original_backend = settings.RESEARCH_ANALYSIS_ENGINE_BACKEND

    def tearDown(self):
        settings.RESEARCH_ANALYSIS_ENGINE_BACKEND = self._original_backend

    def test_default_backend_is_llm(self):
        # Default was "deterministic" for the initial Phase 3 commit
        # (zero behavior change until an operator opted in). Per that
        # commit's own rollout plan step 4, the CEO has since explicitly
        # approved flipping the default to "llm" in a separate follow-up
        # commit - "deterministic" stays fully selectable, just no longer
        # the out-of-the-box default.
        self.assertEqual(settings.RESEARCH_ANALYSIS_ENGINE_BACKEND, "llm")

    def test_deterministic_backend_resolves_to_deterministic_engine(self):
        settings.RESEARCH_ANALYSIS_ENGINE_BACKEND = "deterministic"
        engine = get_analysis_engine()
        self.assertIsInstance(engine, DeterministicAnalysisEngine)

    def test_llm_backend_resolves_to_llm_engine(self):
        settings.RESEARCH_ANALYSIS_ENGINE_BACKEND = "llm"
        engine = get_analysis_engine()
        self.assertIsInstance(engine, LLMAnalysisEngine)

    def test_unknown_backend_raises_keyerror(self):
        settings.RESEARCH_ANALYSIS_ENGINE_BACKEND = "not_a_real_backend"
        with self.assertRaises(KeyError):
            get_analysis_engine()


if __name__ == "__main__":
    unittest.main()
