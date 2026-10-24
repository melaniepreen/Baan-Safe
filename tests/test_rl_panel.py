"""RL panel copy: live = via Mubit; replay/fake never claim a Mubit hop."""

from __future__ import annotations

from paths import ROOT

PANEL = ROOT / "ui" / "sim" / "rl_panel.js"


def test_rl_panel_mubit_source_copy():
    source = PANEL.read_text(encoding="utf-8")
    assert "via Mubit" in source
    assert "live S2 answers via Mubit" in source
    assert "replay from S2 cache (no Mubit call)" in source
    assert "fake S2 (authored truth, no Mubit)" in source
    assert "s2SourceLine" in source
    assert "s2SourceBadge" in source
    assert 'fetch("/rl/run")' in source
    assert "api.mubit.ai" not in source
    assert "MUBIT_" not in source
    assert "OPENROUTER" not in source
    assert "Bearer" not in source
