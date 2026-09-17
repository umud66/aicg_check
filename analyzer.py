from __future__ import annotations

import io
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple

TRANSITIONS = [
    "首先", "其次", "再次", "最后", "此外", "同时", "因此", "由此可见", "综上所述", "总而言之",
    "值得注意的是", "需要指出的是", "需要注意的是", "从而", "进而", "一方面", "另一方面",
    "具体而言", "具体来说", "在此基础上", "基于此", "与此同时", "相较而言", "总体而言",
]
GENERIC_POLICY = [
    "加强", "完善", "健全", "提升", "推动", "促进", "优化", "构建", "建立", "强化", "深化", "推进",
    "保障", "落实", "创新", "规范", "提高", "增强", "形成", "实现", "发挥", "有效", "持续", "进一步",
]
ABSTRACT_NOUNS = [
    "机制", "体系", "水平", "能力", "效能", "质量", "路径", "模式", "格局", "作用", "意义", "价值",
    "需求", "问题", "发展", "建设", "治理", "管理", "服务", "协同", "保障", "改革",
]
AIISH_PATTERNS = [
    r"不仅.{0,18}而且", r"既.{0,18}又", r"一方面.{0,40}另一方面", r"通过.{0,24}(?:进一步|从而|进而|实现)",
    r"有助于.{0,30}(?:提升|推动|促进|增强|实现)", r"对于.{0,30}(?:具有|有着).{0,16}(?:意义|作用|价值)",
    r"在.{0,20}背景下", r"随着.{0,24}(?:发展|推进|变化|提升)", r"从.{0,16}角度来看",
]
CITATION_PATTERNS = [
    r"\[[0-9]{1,3}\]", r"（[^）]{1,30}(?:19|20)\d{2}[^）]*）", r"\([^)]{1,30}(?:19|20)\d{2}[^)]*\)",
]
SKIP_SECTION_PATTERNS = [r"^目录$", r"^参考文献$", r"^致谢$", r"^附录(?:\s|$)"]


@dataclass
class ParagraphResult:
    index: int
    chapter: str
    text: str
    chars: int
    score: float
    level: str
    reasons: str
    transition_density: float
    generic_density: float
    citation_count: int
    digit_density: float
    sentence_cv: float
    repetition_score: float


def _clean_text(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _visible_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[。！？!?；;])", text)
    return [p.strip() for p in parts if _visible_chars(p) >= 4]


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _cv(xs: List[float]) -> float:
    if len(xs) < 2:
        return 1.0
    mean = _mean(xs)
    if not mean:
        return 0.0
    variance = sum((x - mean) ** 2 for x in xs) / len(xs)
    return math.sqrt(variance) / mean


def _count_hits(text: str, lexicon: List[str]) -> int:
    return sum(text.count(item) for item in lexicon)


def _citation_count(text: str) -> int:
    return sum(len(re.findall(pattern, text)) for pattern in CITATION_PATTERNS)


def _digit_density(text: str) -> float:
    chars = _visible_chars(text)
    return len(re.findall(r"\d", text)) / chars if chars else 0.0


def _ngram_repetition(text: str, n: int = 4) -> float:
    compact = re.sub(r"[\s，。！？；：、“”‘’（）()\[\]{}《》,.!?;:\-—]", "", text)
    if len(compact) < n * 3:
        return 0.0
    grams = [compact[i : i + n] for i in range(len(compact) - n + 1)]
    counts = Counter(grams)
    repeated = sum(value - 1 for value in counts.values() if value > 1)
    return min(1.0, repeated / max(1, len(grams)) * 4)


def _pattern_hits(text: str) -> int:
    return sum(1 for pattern in AIISH_PATTERNS if re.search(pattern, text))


def _level(score: float, medium_threshold: int, high_threshold: int) -> str:
    if score >= high_threshold:
        return "高"
    if score >= medium_threshold:
        return "中"
    return "低"


def _is_skipped_section(chapter: str) -> bool:
    normalized = re.sub(r"\s+", "", chapter)
    return any(re.search(pattern, normalized) for pattern in SKIP_SECTION_PATTERNS)


def analyze_paragraph(text: str, index: int, chapter: str, medium_threshold: int = 40, high_threshold: int = 65) -> ParagraphResult:
    text = _clean_text(text)
    chars = _visible_chars(text)
    sentences = _sentences(text)
    lengths = [_visible_chars(sentence) for sentence in sentences]
    sentence_cv = _cv(lengths)

    transition_hits = _count_hits(text, TRANSITIONS)
    generic_hits = _count_hits(text, GENERIC_POLICY)
    abstract_hits = _count_hits(text, ABSTRACT_NOUNS)
    citations = _citation_count(text)
    digits = _digit_density(text)
    repetition = _ngram_repetition(text)
    patterns = _pattern_hits(text)

    transition_density = transition_hits / max(1, chars) * 100
    generic_density = generic_hits / max(1, chars) * 100
    abstract_density = abstract_hits / max(1, chars) * 100

    score = 8.0
    reasons: List[Tuple[float, str]] = []

    if transition_density >= 1.5:
        add = min(18, 7 + transition_density * 4)
        score += add
        reasons.append((add, "模板化连接词密度较高"))
    elif transition_density >= 0.7:
        score += 7
        reasons.append((7, "连接词使用偏规律"))

    if generic_density >= 3.0:
        add = min(18, 6 + generic_density * 2)
        score += add
        reasons.append((add, "“加强/完善/提升/推动”等泛化动词较密集"))
    elif generic_density >= 1.6:
        score += 7
        reasons.append((7, "泛化政策动词偏多"))

    if abstract_density >= 4.0:
        score += 7
        reasons.append((7, "抽象概念密度高、具体信息偏少"))

    if len(lengths) >= 3 and sentence_cv < 0.28:
        add = min(15, (0.28 - sentence_cv) * 45 + 5)
        score += add
        reasons.append((add, "句长分布过于均匀"))
    elif len(lengths) >= 3 and sentence_cv < 0.42:
        score += 5
        reasons.append((5, "句式节奏较规则"))

    if patterns:
        add = min(15, patterns * 5)
        score += add
        reasons.append((add, f"命中 {patterns} 类模板化句式"))

    if repetition >= 0.12:
        add = min(13, repetition * 35)
        score += add
        reasons.append((add, "短语重复度偏高"))

    if chars >= 180 and citations == 0 and digits < 0.006:
        score += 9
        reasons.append((9, "长段落缺少引文/数字等可核查信息"))
    elif chars >= 120 and citations == 0 and digits < 0.003:
        score += 5
        reasons.append((5, "具体事实线索较少"))

    if chars < 45:
        score *= 0.55
    elif chars < 80:
        score *= 0.8

    discount = min(16, citations * 5 + (6 if digits >= 0.02 else 0))
    if discount:
        score -= discount
        reasons.append((-discount, "含引文或数据，降低模板文本风险"))

    score = max(0.0, min(100.0, round(score, 1)))
    positive_reasons = [reason for weight, reason in sorted(reasons, key=lambda item: abs(item[0]), reverse=True) if weight > 0][:4]
    if not positive_reasons:
        positive_reasons = ["未发现明显模板化特征"]

    return ParagraphResult(
        index=index,
        chapter=chapter or "未识别章节",
        text=text,
        chars=chars,
        score=score,
        level=_level(score, medium_threshold, high_threshold),
        reasons="；".join(positive_reasons),
        transition_density=round(transition_density, 2),
        generic_density=round(generic_density, 2),
        citation_count=citations,
        digit_density=round(digits * 100, 2),
        sentence_cv=round(sentence_cv, 3),
        repetition_score=round(repetition, 3),
    )


def extract_docx(data: bytes) -> List[Tuple[str, str]]:
    from docx import Document

    document = Document(io.BytesIO(data))
    rows: List[Tuple[str, str]] = []
    current = "正文"

    for paragraph in document.paragraphs:
        text = _clean_text(paragraph.text)
        if not text:
            continue
        style = (paragraph.style.name or "") if paragraph.style else ""
        is_heading = style.lower().startswith("heading") or style.startswith("标题")
        if not is_heading:
            is_heading = bool(re.match(r"^(第[一二三四五六七八九十百0-9]+[章节篇]|\d+(?:\.\d+){0,3}\s+)", text)) and _visible_chars(text) <= 45
        if is_heading:
            current = text
            continue
        if not _is_skipped_section(current):
            rows.append((current, text))

    return rows


def extract_pdf(data: bytes) -> List[Tuple[str, str]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    rows: List[Tuple[str, str]] = []
    current = "PDF正文"

    for page_no, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").replace("\r", "\n")
        blocks = [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]
        if len(blocks) <= 1:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            blocks = []
            buffer = ""
            for line in lines:
                is_heading = bool(re.match(r"^(第[一二三四五六七八九十百0-9]+[章节篇]|\d+(?:\.\d+){0,3}\s+)", line)) and len(line) <= 45
                if is_heading:
                    if buffer:
                        blocks.append(buffer)
                        buffer = ""
                    blocks.append(line)
                else:
                    buffer += line
                    if line.endswith(("。", "！", "？", ";", "；")) and len(buffer) >= 100:
                        blocks.append(buffer)
                        buffer = ""
            if buffer:
                blocks.append(buffer)

        for block in blocks:
            block = _clean_text(block)
            if not block:
                continue
            is_heading = bool(re.match(r"^(第[一二三四五六七八九十百0-9]+[章节篇]|\d+(?:\.\d+){0,3}\s+)", block)) and _visible_chars(block) <= 45
            if is_heading:
                current = block
                continue
            if not _is_skipped_section(current):
                rows.append((f"{current}（第{page_no}页）", block))

    return rows


def analyze_document(rows: List[Tuple[str, str]], medium_threshold: int = 40, high_threshold: int = 65) -> Tuple[List[ParagraphResult], Dict]:
    results: List[ParagraphResult] = []
    for index, (chapter, text) in enumerate(rows, start=1):
        if _visible_chars(text) < 10:
            continue
        results.append(analyze_paragraph(text, index, chapter, medium_threshold, high_threshold))

    total_chars = sum(result.chars for result in results)
    if not total_chars:
        return results, {"total_chars": 0, "weighted_score": 0, "estimated_ratio": 0, "high_ratio": 0, "medium_high_ratio": 0, "chapters": []}

    weighted_score = sum(result.score * result.chars for result in results) / total_chars
    estimated_ratio = sum(max(0, (result.score - 30) / 70) * result.chars for result in results) / total_chars * 100
    high_chars = sum(result.chars for result in results if result.level == "高")
    medium_high_chars = sum(result.chars for result in results if result.level in ("中", "高"))

    chapter_map = defaultdict(lambda: {"chars": 0, "weighted": 0.0, "high_chars": 0, "mh_chars": 0})
    for result in results:
        item = chapter_map[result.chapter]
        item["chars"] += result.chars
        item["weighted"] += result.score * result.chars
        if result.level == "高":
            item["high_chars"] += result.chars
        if result.level in ("中", "高"):
            item["mh_chars"] += result.chars

    chapters = []
    for chapter, item in chapter_map.items():
        chars = item["chars"]
        chapters.append({
            "chapter": chapter,
            "chars": chars,
            "avg_score": round(item["weighted"] / chars, 1) if chars else 0,
            "high_ratio": round(item["high_chars"] / chars * 100, 1) if chars else 0,
            "medium_high_ratio": round(item["mh_chars"] / chars * 100, 1) if chars else 0,
        })
    chapters.sort(key=lambda item: item["avg_score"], reverse=True)

    summary = {
        "total_chars": total_chars,
        "weighted_score": round(weighted_score, 1),
        "estimated_ratio": round(estimated_ratio, 1),
        "high_ratio": round(high_chars / total_chars * 100, 1),
        "medium_high_ratio": round(medium_high_chars / total_chars * 100, 1),
        "chapters": chapters,
    }
    return results, summary


def results_as_dicts(results: List[ParagraphResult]) -> List[Dict]:
    return [asdict(result) for result in results]
