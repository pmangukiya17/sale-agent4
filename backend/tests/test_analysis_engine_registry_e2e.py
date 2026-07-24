"""
Tests for app/research/analysis/registry.py (get_analysis_engine()) -
M2 Phase 3. Disclosed as NOT executed in the authoring sandbox: this
module imports app.core.config (pydantic_settings) and
DeterministicAnalysisEngine/LLMAnalysisEngine, both of which pull in
SQLAlchemy ORM models - both confirmed absent here, no PyPI/network
access to install them. py_compile-checked clean here; run for real in
Docker.

Run standalone (Docker/full environment only) with:
    python -m unittest tests.test_analysis_engine_registry_e2e
"""
import unittest

from app.core.config import settings
from app.research.analysis.deterministic_stub import DeterministicAnalysisEngine
from app.research.analysis.llm_engine import LLMAnalysisEngine
from app.research.analysis.registry import get_analysis_engine


class TestAnalysisEngineRegistry(unittest.TestCase):
    def setUp(self):
        self._original_backend = settings.RESEARCH_ANALYSIS_ENGINE_BACKEND

    def tearDown(self):
        settings.RESEARCH_ANALYSIS_ENGINE_BACKEND = self._original_backend

    def test_default_backend_is_deterministic(self):
        # The whole point of the config-gated rollout: the default must
        # stay "deterministic" so this phase's own commit changes zero
        # existing behavior until an operator explicitly opts in.
        self.assertEqual(settings.RESEARCH_ANALYSIS_ENGINE_BACKEND, "deterministic")

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
