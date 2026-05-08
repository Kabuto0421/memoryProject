"""GiNZA-backed analyzer for conversational long-term memories."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache

import spacy
from spacy.tokens import Doc, Token


TEXT_EMOTION_RULES = {
    "joy": ["嬉しい", "楽しい", "最高", "安心", "よかった"],
    "sadness": ["悲しい", "寂しい", "つらい", "しんどい"],
    "frustration": ["面倒", "困る", "嫌", "詰まった", "わからない", "おかしくないか"],
    "anxiety": ["不安", "怖い", "心配"],
    "curiosity": ["知りたい", "興味", "試したい"],
}

LEMMA_EMOTION_RULES = {
    "joy": {"嬉しい", "楽しい", "安心"},
    "sadness": {"悲しい", "寂しい", "つらい", "しんどい"},
    "frustration": {"困る", "嫌", "詰まる"},
    "anxiety": {"不安", "怖い", "心配"},
    "curiosity": {"知る", "興味", "試す"},
}

TEXT_MEMORY_TYPE_RULES = {
    "preference": ["好き", "嫌い", "苦手", "避けたい"],
    "desire": ["したい", "ほしい", "欲しい"],
    "worry": ["不安", "心配", "困る", "怖い"],
    "reflection": ["思う", "感じる", "気がする", "おかしくないか", "違和感"],
    "relationship": ["友達", "家族", "母", "父", "恋人", "先輩", "後輩"],
    "decision_support": ["決めてほしい", "選んでほしい", "どれ", "迷う"],
    "task": ["やる", "作る", "確認", "調べる", "直す"],
}

LEMMA_MEMORY_TYPE_RULES = {
    "preference": {"好き", "嫌い", "苦手", "好む", "避ける"},
    "desire": {"望む"},
    "worry": {"不安", "心配", "困る", "怖い"},
    "reflection": {"思う", "感じる", "感ずる", "違和感"},
    "relationship": {"友達", "家族", "母", "父", "恋人", "先輩", "後輩"},
    "decision_support": {"決める", "迷う"},
    "task": {"やる", "作る", "確認", "調べる", "直す"},
}

FUTURE_TERMS = ["明日", "来週", "あとで", "次回", "今度", "締切"]
SENSITIVE_TERMS = ["病気", "トラウマ", "家族", "お金", "秘密", "恋人"]
TECHNICAL_MARKERS = [".py", ".md", "http://", "https://", "/", "SQLite", "FastAPI", "Streamlit"]
SHORT_ACK_TERMS = ["ありがとう", "了解", "OK", "なるほど", "たしかに", "うん", "そうだね"]
TARGET_POS = {"NOUN", "PROPN", "VERB", "ADJ"}
TOPIC_POS = {"NOUN", "PROPN"}
NEGATION_LEMMAS = {"ない", "ぬ", "ず"}
SOFT_NEGATION_CHILD_LEMMAS = {"よう", "ため"}
NEGATION_TARGET_DEPS = {"nsubj", "obj", "iobj", "obl", "advmod", "amod", "ccomp", "xcomp"}


@dataclass(slots=True)
class ParsedText:
    """Intermediate GiNZA parse result used by the analyzer."""

    tokens: list[str]
    lemmas: list[str]
    topics: list[str]
    keywords: list[str]
    entities: list[str]
    negated_lemmas: set[str]
    negated_terms: set[str]


@dataclass(slots=True)
class AnalysisResult:
    """Normalized memory analysis result."""

    summary: str
    topics: list[str]
    keywords: list[str]
    entities: list[str]
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


@lru_cache(maxsize=1)
def get_nlp():
    """Load the GiNZA pipeline once per process."""
    return spacy.load("ja_ginza")


def analyze_text(text: str) -> AnalysisResult:
    """Analyze raw conversational text into memory facets and scores."""
    cleaned = text.strip()
    parsed = _parse_text(cleaned)
    summary = cleaned[:120]
    memory_types = _infer_memory_types(cleaned, parsed)
    emotion = _infer_emotion(cleaned, parsed)
    scores = _score_text(cleaned, parsed, memory_types, emotion)
    reason_codes = _collect_reason_codes(cleaned, parsed, memory_types, emotion)
    save_strength = _score_save_strength(scores, reason_codes)
    memory_priority = _memory_priority(save_strength)
    recall_policy = _build_recall_policy(cleaned, scores)
    safety = _build_safety(cleaned)
    facets = _build_facets(cleaned, parsed, memory_types, emotion)
    return AnalysisResult(
        summary=summary,
        topics=parsed.topics,
        keywords=parsed.keywords,
        entities=parsed.entities,
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


def _parse_text(text: str) -> ParsedText:
    """Parse text with GiNZA and derive normalized tokens."""
    doc = get_nlp()(text)
    tokens = [token.text for token in doc if not token.is_space]
    lemmas = [token.lemma_ for token in doc if not token.is_space]
    entities = _unique_preserve([ent.text for ent in doc.ents if ent.text.strip()])
    topics = _extract_topics(doc, entities)
    keywords = _extract_keywords(doc, entities)
    return ParsedText(
        tokens=tokens,
        lemmas=lemmas,
        topics=topics,
        keywords=keywords,
        entities=entities,
        negated_lemmas={token.lemma_ for token in doc if _is_negated(token)},
        negated_terms={token.text for token in doc if _is_negated(token)},
    )


def _extract_topics(doc: Doc, entities: list[str]) -> list[str]:
    topics: list[str] = []
    topics.extend(entities)
    for token in doc:
        if token.is_space or token.is_stop:
            continue
        if token.pos_ not in TOPIC_POS:
            continue
        candidate = _normalize_token(token)
        if len(candidate) < 2:
            continue
        topics.append(candidate)
    return _unique_preserve(topics)[:6]


def _extract_keywords(doc: Doc, entities: list[str]) -> list[str]:
    keywords: list[str] = []
    keywords.extend(entities)
    for token in doc:
        if token.is_space or token.is_stop:
            continue
        if token.pos_ not in TARGET_POS:
            continue
        candidate = _normalize_token(token)
        if len(candidate) < 2:
            continue
        keywords.append(candidate)
    return _unique_preserve(keywords)[:10]


def _normalize_token(token: Token) -> str:
    """Prefer lemmas when available while preserving useful proper nouns."""
    if token.pos_ == "PROPN":
        return token.text
    lemma = token.lemma_.strip()
    if lemma and lemma != "*":
        return lemma
    return token.text


def _unique_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _infer_memory_types(text: str, parsed: ParsedText) -> list[str]:
    found: list[str] = []
    normalized_text = text.strip()
    lemma_set = set(parsed.keywords) | set(parsed.topics) | set(parsed.lemmas)

    for memory_type, terms in TEXT_MEMORY_TYPE_RULES.items():
        if any(
            term in normalized_text
            and not _is_negated_surface_match(term, parsed)
            for term in terms
        ):
            found.append(memory_type)

    for memory_type, lemmas in LEMMA_MEMORY_TYPE_RULES.items():
        if any(lemma in lemma_set and lemma not in parsed.negated_lemmas for lemma in lemmas):
            found.append(memory_type)

    if not found:
        found.append("context")
    return _unique_preserve(found)


def _infer_emotion(text: str, parsed: ParsedText) -> dict[str, object]:
    matched: list[str] = []
    for emotion, terms in TEXT_EMOTION_RULES.items():
        if any(
            term in text and not _is_negated_surface_match(term, parsed)
            for term in terms
        ):
            matched.append(emotion)

    lemma_set = set(parsed.keywords) | set(parsed.topics) | set(parsed.lemmas)
    for emotion, lemmas in LEMMA_EMOTION_RULES.items():
        if any(lemma in lemma_set and lemma not in parsed.negated_lemmas for lemma in lemmas):
            matched.append(emotion)

    matched = _unique_preserve(matched)
    primary = matched[0] if matched else "neutral"
    intensity = min(1.0, 0.2 + 0.12 * len(matched))
    if "!" in text or "？" in text or "?" in text:
        intensity = min(1.0, intensity + 0.1)
    if parsed.negated_lemmas and primary != "neutral":
        intensity = max(0.2, intensity - 0.05)
    confidence = 0.60 if matched else 0.35
    return {
        "primary": primary,
        "secondary": matched[1:3],
        "valence": _emotion_valence(primary),
        "arousal": round(intensity, 2),
        "intensity": round(intensity, 2),
        "confidence": confidence,
    }


def _emotion_valence(primary: str) -> float:
    if primary in {"joy", "curiosity"}:
        return 0.4
    if primary in {"frustration", "anxiety", "sadness"}:
        return -0.4
    return 0.0


def _collect_reason_codes(
    text: str,
    parsed: ParsedText,
    memory_types: list[str],
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
    if _has_rich_topics(parsed):
        reasons.append("has_rich_topics")
    if parsed.entities:
        reasons.append("has_named_entity")
    if parsed.negated_lemmas:
        reasons.append("has_negation")
    if _is_short_ack(text):
        reasons.append("is_short_ack")
    if len(text) <= 12 and len(parsed.topics) <= 1:
        reasons.append("is_low_information")

    return _unique_preserve(reasons)


def _score_text(
    text: str,
    parsed: ParsedText,
    memory_types: list[str],
    emotion: dict[str, object],
) -> dict[str, float]:
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
    if _has_rich_topics(parsed):
        indexability += 0.2
    if parsed.entities:
        indexability += 0.15
        practical += 0.05
    if any(marker in text for marker in TECHNICAL_MARKERS):
        practical += 0.15
        indexability += 0.15
    if parsed.negated_lemmas:
        affective = max(0.05, affective - 0.08)

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
        0.24 * scores["persistence_value"]
        + 0.18 * scores["affective_value"]
        + 0.16 * scores["identity_value"]
        + 0.16 * scores["relationship_value"]
        + 0.10 * scores["practical_value"]
        + 0.08 * scores["task_value"]
        + 0.08 * scores["retrieval_value"]
    )

    if "has_sensitive_topic" in reason_codes:
        strength += 0.08
    if "has_decision_support" in reason_codes:
        strength += 0.06
    if "has_future_reference" in reason_codes:
        strength += 0.05
    if "has_named_entity" in reason_codes:
        strength += 0.02
    if "has_reflection" in reason_codes:
        strength += 0.05
    if "has_worry" in reason_codes:
        strength += 0.05
    if "has_relationship" in reason_codes:
        strength += 0.06
    if "is_short_ack" in reason_codes:
        strength -= 0.20
    if "is_low_information" in reason_codes:
        strength -= 0.10
    if reason_codes == ["is_context_only"]:
        strength -= 0.08

    return round(max(0.0, min(1.0, strength)), 2)


def _memory_priority(save_strength: float) -> str:
    """Bucket save strength into a simple priority label."""
    if save_strength >= 0.50:
        return "critical"
    if save_strength >= 0.40:
        return "high"
    if save_strength >= 0.22:
        return "medium"
    return "low"


def _is_short_ack(text: str) -> bool:
    """Detect short acknowledgements that should remain low-priority memories."""
    cleaned = text.strip()
    return cleaned in SHORT_ACK_TERMS


def _is_negated_surface_match(term: str, parsed: ParsedText) -> bool:
    """Return True when a surface rule should be softened by negation."""
    return term in parsed.negated_terms or term in parsed.negated_lemmas


def _is_negated(token: Token) -> bool:
    """Return True when a token is modified by a negation marker."""
    if token.is_space or token.lemma_ in NEGATION_LEMMAS:
        return False

    child_lemmas = {child.lemma_ for child in token.children}
    if child_lemmas & SOFT_NEGATION_CHILD_LEMMAS:
        return False
    if any(child.lemma_ in NEGATION_LEMMAS or child.dep_ == "neg" for child in token.children):
        return True

    if token.head is token:
        return False

    head_child_lemmas = {child.lemma_ for child in token.head.children}
    if head_child_lemmas & SOFT_NEGATION_CHILD_LEMMAS:
        return False
    if token.dep_ not in NEGATION_TARGET_DEPS:
        return False
    if token.head.lemma_ in NEGATION_LEMMAS:
        return True
    if any(child.lemma_ in NEGATION_LEMMAS or child.dep_ == "neg" for child in token.head.children):
        return True
    return False


def _has_rich_topics(parsed: ParsedText) -> bool:
    """Return True when the parse carries enough topic variety to matter."""
    return len(parsed.topics) >= 4 or (len(parsed.topics) >= 3 and bool(parsed.entities))


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


def _build_facets(
    text: str,
    parsed: ParsedText,
    memory_types: list[str],
    emotion: dict[str, object],
) -> dict[str, dict[str, object]]:
    return {
        "practical": {
            "goal": "会話文脈で役立つ情報として残す",
            "constraints": ["GiNZA + 簡易ルールベース解析"],
        },
        "emotional": {
            "need": "感情を伴う記憶として扱う" if emotion["primary"] != "neutral" else None,
            "friction": text[:60] if emotion["primary"] in {"frustration", "anxiety"} else None,
        },
        "identity": {
            "values": [memory_type for memory_type in memory_types if memory_type in {"preference", "desire", "reflection"}],
            "self_view": parsed.topics[:2],
        },
        "relationship": {
            "people": [
                topic for topic in parsed.entities + parsed.topics
                if topic in {"友達", "家族", "母", "父", "恋人"}
            ],
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
