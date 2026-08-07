from __future__ import annotations

import runpy
import sys
import urllib.request
from pathlib import Path
from types import TracebackType
from typing import Self

import pytest


class _Response:
    status = 200

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def test_performance_smoke_executes_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = Path(__file__).parents[1] / "scripts" / "performance-smoke.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [str(script), "--url", "http://health.test", "--requests", "2"],
    )
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: _Response())

    runpy.run_path(str(script), run_name="__main__")

    assert "performance smoke passed" in capsys.readouterr().out
