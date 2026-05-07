"""Simple rule-based analyzer for conversational long-term memories."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


WORD_RE = re.compile(r"[A-Za-z0-9_./:-]+|[一-龠ぁ-んァ-ヶー]+")

EMOTION_KEYWORDS = {
    "joy": ["嬉しい", "楽しい", "最高", "安心", "よかった"],
    "sadness": ["悲しい", "寂しい", "つらい", "しんどい"],
    "frustration": ["面倒", "困る", "嫌", "詰まった", "わからない", "おかしくないか"],
    "anxiety": ["不安", "怖い", "心配", "気になる"],
    "curiosity": ["気になる", "知りたい", "興味", "試したい"],
}

MEMORY_TYPE_RULES = {
    "preference": ["好き", "嫌い", "苦手", "好む", "避けたい"],
    "desire": ["したい", "ほしい", "欲しい", "望む"],
    "worry": ["不安", "心配", "困る", "怖い"],
    "reflection": ["思う", "感じる", "おかしくないか", "違和感"],
    "relationship": ["友達", "家族", "母", "父", "恋人", "先輩", "後輩"],
    "decision_support": ["決めてほしい", "選んでほしい", "どれ", "迷う"],
    "task": ["やる", "作る", "確認", "調べる", "直す"],
}

FUTURE_TERMS = ["明日", "来週", "あとで", "次回", "今度", "締切"]
SENSITIVE_TERMS = ["病気", "トラウマ", "家族", "お金", "秘密", "恋人"]
TECHNICAL_MARKERS = [".py", ".md", "http://", "https://", "/", "SQLite", "FastAPI", "Streamlit"]
SHORT_ACK_TERMS = ["ありがとう", "了解", "OK", "なるほど", "たしかに", "うん", "そうだね"]


@dataclass(slots=True)
class AnalysisResult:
    """Normalized memory analysis result."""

    summary: str
    topics: list[str]
    keywords: list[str]
    memory_types: list[str]
    facets: dict[str, dict[str, object]]
    scores: dict[str, float]
    emotion: dict[str, object]
    recall_policy: dict[str, object]
    safety: dict[str, object]
    save_strength: float
    memory_priority: str
    reason_codes: list[str]

    def to_dict(self) -> dict[str, object]:
        """Convert the result into a plain JSON-serializable dictionary."""
        return asdict(self)


def analyze_text(text: str) -> AnalysisResult:
    """Analyze raw conversational text into memory facets and scores."""
    cleaned = text.strip()
    tokens = WORD_RE.findall(cleaned)
    unique_tokens = _unique_preserve(tokens)
    summary = cleaned[:120]
    topics = unique_tokens[:5]
    keywords = _extract_keywords(unique_tokens)
    memory_types = _infer_memory_types(cleaned)
    emotion = _infer_emotion(cleaned)
    scores = _score_text(cleaned, memory_types, topics, emotion)
    reason_codes = _collect_reason_codes(cleaned, memory_types, topics, emotion)
    save_strength = _score_save_strength(scores, reason_codes)
    memory_priority = _memory_priority(save_strength)
    recall_policy = _build_recall_policy(cleaned, scores)
    safety = _build_safety(cleaned)
    facets = _build_facets(cleaned, memory_types, emotion, topics)
    return AnalysisResult(
        summary=summary,
        topics=topics,
        keywords=keywords,
        memory_types=memory_types,
        facets=facets,
        scores=scores,
        emotion=emotion,
        recall_policy=recall_policy,
        safety=safety,
        save_strength=save_strength,
        memory_priority=memory_priority,
        reason_codes=reason_codes,
    )


def _unique_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _extract_keywords(tokens: list[str]) -> list[str]:
    return [token for token in tokens if len(token) >= 2][:8]


def _infer_memory_types(text: str) -> list[str]:
    found: list[str] = []
    for memory_type, terms in MEMORY_TYPE_RULES.items():
        if any(term in text for term in terms):
            found.append(memory_type)
    if not found:
        found.append("context")
    return found


def _infer_emotion(text: str) -> dict[str, object]:
    matched: list[str] = []
    for emotion, terms in EMOTION_KEYWORDS.items():
        if any(term in text for term in terms):
            matched.append(emotion)
    primary = matched[0] if matched else "neutral"
    intensity = min(1.0, 0.2 + 0.15 * len(matched))
    if "!" in text or "？" in text or "?" in text:
        intensity = min(1.0, intensity + 0.1)
    return {
        "primary": primary,
        "secondary": matched[1:3],
        "valence": _emotion_valence(primary),
        "arousal": round(intensity, 2),
        "intensity": round(intensity, 2),
        "confidence": 0.55 if matched else 0.35,
    }


def _emotion_valence(primary: str) -> float:
    if primary in {"joy", "curiosity"}:
        return 0.4
    if primary in {"frustration", "anxiety", "sadness"}:
        return -0.4
    return 0.0


def _collect_reason_codes(
    text: str,
    memory_types: list[str],
    topics: list[str],
    emotion: dict[str, object],
) -> list[str]:
    """Collect human-readable reason codes for why a memory matters."""
    reasons: list[str] = []
    mapping = {
        "preference": "has_preference",
        "desire": "has_desire",
        "worry": "has_worry",
        "reflection": "has_reflection",
        "relationship": "has_relationship",
        "decision_support": "has_decision_support",
        "task": "has_task_signal",
        "context": "is_context_only",
    }
    for memory_type in memory_types:
        code = mapping.get(memory_type)
        if code:
            reasons.append(code)

    if any(term in text for term in FUTURE_TERMS):
        reasons.append("has_future_reference")
    if emotion["primary"] != "neutral":
        reasons.append("has_emotion_signal")
    if any(term in text for term in SENSITIVE_TERMS):
        reasons.append("has_sensitive_topic")
    if any(marker in text for marker in TECHNICAL_MARKERS):
        reasons.append("has_technical_marker")
    if len(topics) >= 3:
        reasons.append("has_rich_topics")
    if _is_short_ack(text):
        reasons.append("is_short_ack")
    if len(text) <= 12 and len(topics) <= 1:
        reasons.append("is_low_information")

    return _unique_preserve(reasons)


def _score_text(text: str, memory_types: list[str], topics: list[str], emotion: dict[str, object]) -> dict[str, float]:
    persistence = 0.35
    retrieval = 0.25
    affective = 0.2
    identity = 0.2
    relationship = 0.05
    practical = 0.15
    task = 0.05
    decision = 0.05
    indexability = 0.2

    if any(term in text for term in FUTURE_TERMS):
        retrieval += 0.25
        task += 0.1
    if "preference" in memory_types or "desire" in memory_types:
        persistence += 0.15
        identity += 0.2
    if "reflection" in memory_types:
        persistence += 0.1
        identity += 0.15
    if "decision_support" in memory_types:
        practical += 0.25
        decision += 0.2
        retrieval += 0.1
    if "task" in memory_types:
        task += 0.35
        practical += 0.15
    if "relationship" in memory_types:
        relationship += 0.5
        persistence += 0.1
    if emotion["primary"] != "neutral":
        affective += 0.35
        persistence += 0.1
    if len(topics) >= 3:
        indexability += 0.2
    if any(marker in text for marker in TECHNICAL_MARKERS):
        practical += 0.15
        indexability += 0.15

    return {
        "persistence_value": round(min(1.0, persistence), 2),
        "retrieval_value": round(min(1.0, retrieval), 2),
        "affective_value": round(min(1.0, affective), 2),
        "identity_value": round(min(1.0, identity), 2),
        "relationship_value": round(min(1.0, relationship), 2),
        "practical_value": round(min(1.0, practical), 2),
        "task_value": round(min(1.0, task), 2),
        "decision_value": round(min(1.0, decision), 2),
        "indexability_value": round(min(1.0, indexability), 2),
    }


def _score_save_strength(scores: dict[str, float], reason_codes: list[str]) -> float:
    """Compute a unified save strength while keeping all memories stored."""
    strength = (
        0.30 * scores["persistence_value"]
        + 0.20 * scores["affective_value"]
        + 0.15 * scores["identity_value"]
        + 0.10 * scores["relationship_value"]
        + 0.10 * scores["practical_value"]
        + 0.10 * scores["task_value"]
        + 0.05 * scores["retrieval_value"]
    )

    if "has_sensitive_topic" in reason_codes:
        strength += 0.05
    if "has_decision_support" in reason_codes:
        strength += 0.05
    if "has_future_reference" in reason_codes:
        strength += 0.04
    if "is_short_ack" in reason_codes:
        strength -= 0.18
    if "is_low_information" in reason_codes:
        strength -= 0.10
    if reason_codes == ["is_context_only"]:
        strength -= 0.08

    return round(max(0.0, min(1.0, strength)), 2)


def _memory_priority(save_strength: float) -> str:
    """Bucket save strength into a simple priority label."""
    if save_strength >= 0.80:
        return "critical"
    if save_strength >= 0.55:
        return "high"
    if save_strength >= 0.30:
        return "medium"
    return "low"


def _is_short_ack(text: str) -> bool:
    """Detect short acknowledgements that should remain low-priority memories."""
    cleaned = text.strip()
    return cleaned in SHORT_ACK_TERMS


def _build_recall_policy(text: str, scores: dict[str, float]) -> dict[str, object]:
    allowed_contexts = ["related_topic"]
    if scores["practical_value"] >= 0.35:
        allowed_contexts.append("decision_support")
    if scores["task_value"] >= 0.3:
        allowed_contexts.append("follow_up")
    if scores["affective_value"] >= 0.45:
        allowed_contexts.append("emotional_support")

    avoid_contexts = ["unrelated_smalltalk"] if scores["affective_value"] >= 0.45 else []
    mode = "gentle" if scores["affective_value"] >= 0.45 else "normal"
    if any(term in text for term in SENSITIVE_TERMS):
        mode = "explicit_only"
        avoid_contexts.append("casual_joking")

    return {
        "mode": mode,
        "allowed_contexts": allowed_contexts,
        "avoid_contexts": avoid_contexts,
        "suggested_phrasing": f"以前、{text[:40]}...という話があったけど",
        "auto_recall_threshold": 0.75 if mode == "gentle" else 0.65,
    }


def _build_safety(text: str) -> dict[str, object]:
    sensitivity = "sensitive" if any(term in text for term in SENSITIVE_TERMS) else "normal"
    return {
        "sensitivity": sensitivity,
        "privacy_level": "personal",
        "stability": "medium",
        "source_confidence": 0.9,
        "needs_confirmation": False,
    }


def _build_facets(text: str, memory_types: list[str], emotion: dict[str, object], topics: list[str]) -> dict[str, dict[str, object]]:
    return {
        "practical": {
            "goal": "会話文脈で役立つ情報として残す",
            "constraints": ["簡易ルールベース解析"],
        },
        "emotional": {
            "need": "感情を伴う記憶として扱う" if emotion["primary"] != "neutral" else None,
            "friction": text[:60] if emotion["primary"] in {"frustration", "anxiety"} else None,
        },
        "identity": {
            "values": [memory_type for memory_type in memory_types if memory_type in {"preference", "desire", "reflection"}],
            "self_view": topics[:2],
        },
        "relationship": {
            "people": [topic for topic in topics if topic in {"友達", "家族", "母", "父", "恋人"}],
            "relation_context": "personal" if "relationship" in memory_types else None,
        },
        "task": {
            "open_tasks": [text[:80]] if "task" in memory_types else [],
            "deadlines": [term for term in FUTURE_TERMS if term in text],
        },
        "decision": {
            "decisions": [text[:80]] if "decision_support" in memory_types else [],
            "rejected_options": [],
        },
    }
