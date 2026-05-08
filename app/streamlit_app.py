"""Review-oriented Streamlit UI for the conversational memory MVP."""

from pathlib import Path
import sys
from typing import Any

import streamlit as st

# Ensure the project root is importable when Streamlit executes this file directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.memory.store import create_message, init_db, list_messages, list_relevant_context, list_shared_contexts

SPEAKER_OPTIONS = ("user", "assistant")
MEMORY_SCOPE_OPTIONS = ("all", "user_memory", "assistant_trace", "shared_context_candidate")
STATUS_OPTIONS = ("all", "asserted", "proposed", "accepted", "rejected", "unresolved")
PRIORITY_OPTIONS = ("all", "low", "medium", "high", "critical")

st.set_page_config(page_title="Long Memory Prototype", page_icon="🧠", layout="wide")
st.title("Long Memory Prototype")
st.caption("会話ターンの保存、shared context の確認、想起候補の点検を一つの画面で行う。")

init_db()


def _reason_code_text(reason_codes: list[str]) -> str:
    if not reason_codes:
        return "-"
    return " ".join(f"`{code}`" for code in reason_codes)


def _is_suspicious(memory: dict[str, Any]) -> bool:
    reason_codes = set(memory["reason_codes"])
    if memory["memory_priority"] == "low" and (
        {"has_shared_context_signal", "has_relationship", "has_worry", "has_reflection"} & reason_codes
    ):
        return True
    if memory["memory_priority"] in {"high", "critical"} and (
        {"is_short_ack", "is_low_information"} & reason_codes
    ):
        return True
    return False


def _matches_priority(memory: dict[str, Any], priority_filter: str) -> bool:
    return priority_filter == "all" or memory["memory_priority"] == priority_filter


with st.form("message_form"):
    st.subheader("新規メッセージ保存")
    speaker = st.segmented_control(
        "speaker",
        options=SPEAKER_OPTIONS,
        default="user",
        help="この会話ターンの話者。",
    )
    text = st.text_area(
        "保存したい会話ターン",
        height=140,
        placeholder="例: 本屋で本を選ぶのが面倒で、AIに一冊決めてほしいと感じた。",
    )
    meta_col1, meta_col2 = st.columns(2)
    with meta_col1:
        turn_id = st.text_input("turn_id（任意）", placeholder="未入力なら自動採番")
    with meta_col2:
        reply_to_turn_id = st.text_input("reply_to_turn_id（任意）", placeholder="返信元 turn_id があれば入力")
    submitted = st.form_submit_button("保存する")

if submitted:
    if text.strip():
        message = create_message(
            text,
            speaker=speaker,
            turn_id=turn_id or None,
            reply_to_turn_id=reply_to_turn_id or None,
        )
        st.success(f"保存した: {message['id']}")
        st.info(
            f"turn_id={message['turn_id']} | "
            f"speaker={message['speaker']} | "
            f"scope={message['memory_scope']} | "
            f"status={message['status']} | "
            f"priority={message['memory_priority']} | "
            f"save_strength={message['save_strength']}"
        )
        st.caption(f"reason_codes: {', '.join(message['reason_codes'])}")
        st.json(message, expanded=False)
    else:
        st.warning("空の文章は保存できない。")

messages_tab, contexts_tab, relevant_tab = st.tabs(
    ["メッセージレビュー", "Shared Context", "想起プレビュー"]
)

with messages_tab:
    st.subheader("保存済みメッセージ")
    filter_col1, filter_col2, filter_col3, filter_col4, filter_col5, filter_col6 = st.columns(6)
    with filter_col1:
        speaker_filter = st.selectbox("speaker", options=SPEAKER_OPTIONS, index=None, placeholder="all")
    with filter_col2:
        scope_filter = st.selectbox("memory_scope", options=MEMORY_SCOPE_OPTIONS, index=0)
    with filter_col3:
        status_filter = st.selectbox("status", options=STATUS_OPTIONS, index=0)
    with filter_col4:
        priority_filter = st.selectbox("priority", options=PRIORITY_OPTIONS, index=0)
    with filter_col5:
        suspicious_only = st.checkbox("suspicious only", value=False)
    with filter_col6:
        limit = st.slider("limit", min_value=5, max_value=50, value=20, step=5)

    messages = list_messages(
        limit=limit,
        speaker=speaker_filter,
        memory_scope=None if scope_filter == "all" else scope_filter,
        status=None if status_filter == "all" else status_filter,
    )
    messages = [message for message in messages if _matches_priority(message, priority_filter)]
    if suspicious_only:
        messages = [message for message in messages if _is_suspicious(message)]

    st.caption(
        f"表示件数: {len(messages)} | "
        f"speaker={speaker_filter or 'all'} | "
        f"memory_scope={scope_filter} | "
        f"status={status_filter} | "
        f"priority={priority_filter}"
    )

    for message in messages:
        with st.container(border=True):
            flags: list[str] = []
            if _is_suspicious(message):
                flags.append("suspicious")
            if message["status"] == "accepted":
                flags.append("accepted")
            header = message["summary"]
            if flags:
                header += f" [{' / '.join(flags)}]"
            st.markdown(f"**{header}**")
            st.write(message["raw_text"])
            st.caption(
                f"turn_id={message['turn_id']} | "
                f"reply_to={message['reply_to_turn_id'] or '-'} | "
                f"speaker={message['speaker']} | "
                f"scope={message['memory_scope']} | "
                f"status={message['status']} | "
                f"priority={message['memory_priority']} | "
                f"save_strength={message['save_strength']} | "
                f"emotion={message['emotion']['primary']} | "
                f"created_at={message['created_at']}"
            )
            st.markdown(f"reason_codes: {_reason_code_text(message['reason_codes'])}")
            st.json(message, expanded=False)

with contexts_tab:
    st.subheader("Shared Context 一覧")
    context_limit = st.slider("shared context limit", min_value=5, max_value=50, value=20, step=5)
    shared_contexts = list_shared_contexts(limit=context_limit)
    st.caption(f"表示件数: {len(shared_contexts)}")

    for context in shared_contexts:
        with st.container(border=True):
            st.markdown(f"**{context['summary']}**")
            st.write(context["detail"])
            st.caption(
                f"id={context['id']} | "
                f"status={context['status']} | "
                f"importance={context['importance']} | "
                f"created_at={context['created_at']}"
            )
            st.markdown(f"source_turn_ids: `{', '.join(context['source_turn_ids'])}`")
            st.markdown(f"tags: {', '.join(f'`{tag}`' for tag in context['tags']) if context['tags'] else '-'}")
            st.json(context, expanded=False)

with relevant_tab:
    st.subheader("想起プレビュー")
    query = st.text_input("query", placeholder="例: 保存方針 / 本屋 / 家族 / README")
    relevant_col1, relevant_col2, relevant_col3, relevant_col4 = st.columns(4)
    with relevant_col1:
        relevant_speaker = st.selectbox("speaker filter", options=SPEAKER_OPTIONS, index=None, placeholder="all", key="relevant_speaker")
    with relevant_col2:
        relevant_scope = st.selectbox("scope filter", options=MEMORY_SCOPE_OPTIONS, index=0, key="relevant_scope")
    with relevant_col3:
        relevant_priority = st.selectbox("priority filter", options=PRIORITY_OPTIONS, index=0, key="relevant_priority")
    with relevant_col4:
        relevant_limit = st.slider("result limit", min_value=3, max_value=15, value=8, step=1)

    if query.strip():
        result = list_relevant_context(
            query,
            limit=relevant_limit,
            speaker=relevant_speaker,
            memory_priority=None if relevant_priority == "all" else relevant_priority,
            memory_scope=None if relevant_scope == "all" else relevant_scope,
        )
        st.caption(
            f"shared_contexts={len(result['shared_contexts'])} | "
            f"memories={len(result['memories'])}"
        )

        st.markdown("### Shared Context 候補")
        if result["shared_contexts"]:
            for context in result["shared_contexts"]:
                with st.container(border=True):
                    st.markdown(f"**{context['summary']}**")
                    st.caption(
                        f"id={context['id']} | "
                        f"importance={context['importance']} | "
                        f"status={context['status']}"
                    )
                    st.markdown(f"source_turn_ids: `{', '.join(context['source_turn_ids'])}`")
        else:
            st.info("shared context は見つからなかった。")

        st.markdown("### Raw Memory 候補")
        if result["memories"]:
            for memory in result["memories"]:
                with st.container(border=True):
                    st.markdown(f"**{memory['summary']}**")
                    st.write(memory["raw_text"])
                    st.caption(
                        f"turn_id={memory['turn_id']} | "
                        f"speaker={memory['speaker']} | "
                        f"scope={memory['memory_scope']} | "
                        f"priority={memory['memory_priority']} | "
                        f"save_strength={memory['save_strength']}"
                    )
                    st.markdown(f"reason_codes: {_reason_code_text(memory['reason_codes'])}")
        else:
            st.info("raw memory は見つからなかった。")
    else:
        st.info("query を入れると、今の初期想起ロジックで relevant context を確認できる。")
