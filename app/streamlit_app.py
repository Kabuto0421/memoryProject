"""Minimal Streamlit UI for the conversational memory MVP."""

from pathlib import Path
import sys

import streamlit as st

# Ensure the project root is importable when Streamlit executes this file directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.memory.store import create_memory, init_db, list_memories

st.set_page_config(page_title="Long Memory Prototype", page_icon="🧠")
st.title("Long Memory Prototype")
st.caption("日常会話を簡易解析して、感情付きの長期記憶として保存する。")

init_db()

with st.form("memory_form"):
    raw_text = st.text_area(
        "記憶したい会話文",
        height=140,
        placeholder="例: 本屋で本を選ぶのが面倒で、AIに一冊決めてほしいと感じた。",
    )
    submitted = st.form_submit_button("保存する")

if submitted:
    if raw_text.strip():
        memory = create_memory(raw_text)
        st.success(f"保存した: {memory['id']}")
        st.info(
            f"save_strength={memory['save_strength']} | "
            f"priority={memory['memory_priority']} | "
            f"reasons={', '.join(memory['reason_codes'])}"
        )
    else:
        st.warning("空の文章は保存できない。")

st.subheader("保存済み記憶")
for memory in list_memories(limit=20):
    with st.container(border=True):
        st.markdown(f"**{memory['summary']}**")
        st.write(memory["raw_text"])
        st.caption(
            f"types={', '.join(memory['memory_types'])} | "
            f"emotion={memory['emotion']['primary']} | "
            f"priority={memory['memory_priority']} | "
            f"save_strength={memory['save_strength']} | "
            f"created_at={memory['created_at']}"
        )
        st.json(memory, expanded=False)
