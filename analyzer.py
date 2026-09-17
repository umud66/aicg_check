"""Compatibility shim for the current analyzer implementation.

The public import surface stays stable for app.py, tests and benchmark.py while
v0.4 lives in analyzer_v04.py.
"""

import analyzer_v04 as _engine
from analyzer_v04 import *  # noqa: F401,F403

# User-requested rule removal: a long paragraph is no longer considered risky
# merely because it contains no citation / numeric evidence. Literature-review
# citation-gap analysis remains a separate, section-specific signal.
_original_base_features = _engine._base_features


def _base_features_without_long_paragraph_rule(text, profile="general", section="body"):
    data = _original_base_features(text, profile, section)
    kept = []
    removed_weight = 0.0
    for weight, reason in data.get("reasons", []):
        if reason == "长段落缺少可核查事实或引文":
            removed_weight += max(0.0, float(weight))
            continue
        kept.append((weight, reason))
    if removed_weight:
        data["score"] = max(4.0, float(data.get("score", 0.0)) - removed_weight)
        data["reasons"] = kept
    return data


_engine._base_features = _base_features_without_long_paragraph_rule
