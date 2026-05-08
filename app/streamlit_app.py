"""Minimal Streamlit UI for the conversational memory MVP."""

from pathlib import Path
import sys

import streamlit as st

# Ensure the project root is importable when Streamlit executes this file directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.memory.store import create_message, init_db, list_messages

SPEAKER_OPTIONS = ("user", "assistant")
MEMORY_SCOPE_OPTIONS = ("all", "user_memory", "assistant_trace", "shared_context_candidate")
STATUS_OPTIONS = ("all", "asserted", "proposed", "accepted", "rejected", "unresolved")

st.set_page_config(page_title="Long Memory Prototype", page_icon="🧠")
st.title("Long Memory Prototype")
st.caption("会話ターンを保存し、日常会話向けの長期記憶として構造化する。")

init_db()

with st.form("message_form"):
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
    turn_id = st.text_input(
        "turn_id（任意）",
        placeholder="未入力なら自動採番",
    )
    reply_to_turn_id = st.text_input(
        "reply_to_turn_id（任意）",
        placeholder="返信元 turn_id があれば入力",
    )
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

st.subheader("保存済みメッセージ")

filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
with filter_col1:
    speaker_filter = st.selectbox("speaker filter", options=SPEAKER_OPTIONS, index=None, placeholder="all")
with filter_col2:
    scope_filter = st.selectbox("memory_scope filter", options=MEMORY_SCOPE_OPTIONS, index=0)
with filter_col3:
    status_filter = st.selectbox("status filter", options=STATUS_OPTIONS, index=0)
with filter_col4:
    limit = st.slider("limit", min_value=5, max_value=50, value=20, step=5)

messages = list_messages(
    limit=limit,
    speaker=speaker_filter,
    memory_scope=None if scope_filter == "all" else scope_filter,
    status=None if status_filter == "all" else status_filter,
)

st.caption(
    f"表示件数: {len(messages)} | "
    f"speaker={speaker_filter or 'all'} | "
    f"memory_scope={scope_filter} | "
    f"status={status_filter}"
)

for message in messages:
    with st.container(border=True):
        st.markdown(f"**{message['summary']}**")
        st.write(message["raw_text"])
        st.caption(
            f"turn_id={message['turn_id']} | "
            f"reply_to={message['reply_to_turn_id'] or '-'} | "
            f"speaker={message['speaker']} | "
            f"scope={message['memory_scope']} | "
            f"status={message['status']} | "
            f"priority={message['memory_priority']} | "
            f"emotion={message['emotion']['primary']} | "
            f"created_at={message['created_at']}"
        )
        st.json(message, expanded=False)
