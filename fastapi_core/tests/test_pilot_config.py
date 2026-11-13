"""T6 pilot-config: the FastAPI AI dependency is config-driven. It refuses 403 while ENABLE_AI_FEATURES
is off (pilot default), and keeps refusing 403 while RAG is unverified. Tests only auth.disabled_in_phase1
— no torch/model needed. Run from fastapi_core/:  python -m unittest tests.test_pilot_config -v"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import auth  # noqa: E402


class AIDisabledDependencyTests(unittest.TestCase):
    def test_403_when_ai_features_off(self):
        with mock.patch.dict(os.environ, {'ENABLE_AI_FEATURES': '0'}, clear=False):
            with self.assertRaises(HTTPException) as ctx:
                auth.disabled_in_phase1({'roles': ['SchoolAdmin']})
        self.assertEqual(ctx.exception.status_code, 403)

    def test_403_default_when_flag_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as ctx:
                auth.disabled_in_phase1({'roles': ['SchoolAdmin']})
        self.assertEqual(ctx.exception.status_code, 403)

    def test_still_403_when_flag_on_rag_unverified(self):
        with mock.patch.dict(os.environ, {'ENABLE_AI_FEATURES': '1'}, clear=False):
            with self.assertRaises(HTTPException) as ctx:
                auth.disabled_in_phase1({'roles': ['SchoolAdmin']})
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == '__main__':
    unittest.main()
