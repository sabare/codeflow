from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from backend import analyzer


class AnalyzerSafetyTests(unittest.TestCase):
    def test_build_analysis_raises_when_analyzer_import_is_missing(self) -> None:
        with mock.patch.object(analyzer, "_raw_build_analysis", None):
            with mock.patch.dict(os.environ, {analyzer.DEV_MOCK_MODE_ENV: ""}, clear=False):
                with self.assertRaises(RuntimeError):
                    analyzer.build_analysis(Path("."))

    def test_build_analysis_uses_mock_only_when_dev_mode_enabled(self) -> None:
        with mock.patch.object(analyzer, "_raw_build_analysis", None):
            with mock.patch.dict(os.environ, {analyzer.DEV_MOCK_MODE_ENV: "1"}, clear=False):
                result = analyzer.build_analysis(Path("."))

        self.assertIn("tree", result)

    def test_build_analysis_raises_when_real_analyzer_crashes(self) -> None:
        def _crash(_: Path) -> dict:
            raise ValueError("boom")

        with mock.patch.object(analyzer, "_raw_build_analysis", _crash):
            with mock.patch.dict(os.environ, {analyzer.DEV_MOCK_MODE_ENV: ""}, clear=False):
                with self.assertRaises(RuntimeError):
                    analyzer.build_analysis(Path("."))


if __name__ == "__main__":
    unittest.main()
