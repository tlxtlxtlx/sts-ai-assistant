from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "update_community_knowledge.py"

spec = importlib.util.spec_from_file_location("update_community_knowledge", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
assert spec.loader is not None
spec.loader.exec_module(module)


def test_should_fetch_url_skips_local_curated_sources() -> None:
    assert module.should_fetch_url("https://community.local/silent/corpse-poison") is False
    assert module.should_fetch_url("https://www.reddit.com/r/slaythespire/") is True


def test_build_source_entry_uses_local_fallback_without_network() -> None:
    seed_source = {
        "source_id": "unit_local_source",
        "url": "https://community.local/unit/test",
        "publisher": "Curated Community Notes",
        "character_classes": ["THE_SILENT"],
        "tags": ["curated", "tier_s"],
        "fallback_title": "??????",
        "fallback_summary": "????",
        "fallback_excerpt": "????",
        "fallback_published_at": "2026-03",
    }

    entry = module.build_source_entry(seed_source)

    assert entry.title == "??????"
    assert entry.summary == "????"
    assert entry.excerpt == "????"
    assert entry.raw_status == "fallback"
