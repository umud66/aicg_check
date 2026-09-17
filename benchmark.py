from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import List, Tuple

from analyzer import analyze_document


def load_csv(path: Path) -> List[Tuple[int, str]]:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            label = int(row["label"])
            text = row["text"].strip()
            if text:
                rows.append((label, text))
    return rows


def auc(points: List[Tuple[int, float]]) -> float:
    pos = [s for y, s in points if y == 1]
    neg = [s for y, s in points if y == 0]
    if not pos or not neg:
        return 0.0
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1 if p > n else 0.5 if p == n else 0
    return wins / (len(pos) * len(neg))


def metrics(points: List[Tuple[int, float]], threshold: float) -> dict:
    tp = fp = tn = fn = 0
    for y, score in points:
        pred = score >= threshold
        if y == 1 and pred: tp += 1
        elif y == 0 and pred: fp += 1
        elif y == 0: tn += 1
        else: fn += 1
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {"threshold": threshold, "precision": precision, "recall": recall, "f1": f1, "false_positive_rate": fp / (fp + tn) if fp + tn else 0, "tp": tp, "fp": fp, "tn": tn, "fn": fn}


def main() -> None:
    parser = argparse.ArgumentParser(description="AICG Check 离线标注集评估")
    parser.add_argument("dataset", type=Path, help="CSV: label,text；label=1 表示 AI/高AI参与，0 表示人工")
    parser.add_argument("--profile", default="general", choices=["general", "public_management", "strict"])
    args = parser.parse_args()
    samples = load_csv(args.dataset)
    scored = []
    for label, text in samples:
        results, _ = analyze_document([("样本", text)], profile=args.profile)
        scored.append((label, results[0].score if results else 0.0))
    candidates = [x / 2 for x in range(40, 181)]
    scored_metrics = [metrics(scored, t) for t in candidates]
    best = max(scored_metrics, key=lambda x: x["f1"]) if scored_metrics else {}
    report = {"samples": len(scored), "positive": sum(y for y, _ in scored), "negative": sum(1-y for y, _ in scored), "auc": round(auc(scored), 4), "best_f1": {k: round(v, 4) if isinstance(v, float) else v for k, v in best.items()}}
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
