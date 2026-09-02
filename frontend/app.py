import streamlit as st
import sys
import os
import base64
import io
from datetime import date, datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.brain import EchoBrain
from backend.sentiment import MOOD_EMOJI
from backend.reminders import TYPE_EMOJI

st.set_page_config(
    page_title="EchoMemory Companion",
    page_icon="🌸",
    layout="centered"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400&family=Source+Sans+3:wght@400;600&display=swap');
    html, body, [class*="css"] { font-family: 'Source Sans 3', sans-serif; font-size: 18px; }
    h1 { font-family: 'Lora', serif; font-size: 2rem !important; color: #4a3728; }
    .stChatMessage { font-size: 18px; line-height: 1.7; }

    [data-testid="stSidebar"] { background-color: #2c1f14 !important; }
    [data-testid="stSidebar"] * { color: #f5e6d3 !important; }
    [data-testid="stSidebar"] .stButton button {
        background-color: #5c3d2e !important; color: #f5e6d3 !important;
        border: 1px solid #8b6347 !important;
    }
    [data-testid="stSidebar"] .stButton button:hover { background-color: #7a5240 !important; }
    [data-testid="stSidebar"] .stTextInput input,
    [data-testid="stSidebar"] .stSelectbox select,
    [data-testid="stSidebar"] .stTimeInput input {
        background-color: #3d2a1e !important; color: #f5e6d3 !important;
        border: 1px solid #8b6347 !important;
    }
    [data-testid="stSidebar"] .stSuccess { background-color: #1e3d2a !important; }
    [data-testid="stSidebar"] .stWarning { background-color: #3d2e1e !important; }

    .mood-bar {
        display: flex; align-items: center; gap: 8px;
        padding: 6px 12px; background: #fdf6ee;
        border-radius: 20px; border: 1px solid #e0cfc0;
        font-size: 15px; margin-bottom: 8px; width: fit-content;
    }
    .reminder-alert {
        background: #e8f4fd; border: 1px solid #90caf9;
        border-radius: 10px; padding: 10px 16px;
        font-size: 16px; margin-bottom: 10px;
    }
    .alert-box {
        background: #fff3cd; border: 1px solid #ffc107;
        border-radius: 10px; padding: 10px 16px;
        font-size: 16px; margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)


#  Helpers 
def speak(text: str):
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang='en', slow=True)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()
        st.markdown(
            f'<audio autoplay><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>',
            unsafe_allow_html=True
        )
    except Exception:
        pass


def listen() -> str | None:
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        r.energy_threshold = 3000
        r.pause_threshold = 1.5
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=8, phrase_time_limit=15)
        return r.recognize_google(audio)
    except Exception:
        return None


#  Initialize 
if "echo" not in st.session_state:
    with st.spinner("Waking up Kuttymani..."):
        st.session_state.echo = EchoBrain()
        os.makedirs("data/photos", exist_ok=True)
        try:
            with open("data/family_memories.txt", "r", encoding="utf-8") as f:
                content = f.read()
            st.session_state.echo.initialize_memory(content)
            st.session_state.memory_loaded = True
        except FileNotFoundError:
            st.session_state.memory_loaded = False

if "tts_enabled" not in st.session_state:
    st.session_state.tts_enabled = True
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": "Hello! I am Kuttymani. How can I help you remember your family today?",
        "mood": "calm", "mood_emoji": "😌"
    }]
if "show_photo_upload" not in st.session_state:
    st.session_state.show_photo_upload = False
if "current_mood" not in st.session_state:
    st.session_state.current_mood = "calm"
if "current_mood_emoji" not in st.session_state:
    st.session_state.current_mood_emoji = "😌"


#  Sidebar 
with st.sidebar:
    st.title("🌸 EchoMemory")
    st.write("A caring memory companion.")
    st.divider()

    # Memory status
    if st.session_state.get("memory_loaded"):
        st.success(" Family Records Loaded...")
    else:
        st.warning(" No family_memories.txt found in /data")

    st.divider()

    #  Reminders panel 
    st.subheader("⏰ Reminders")

    # Today's reminders
    todays = st.session_state.echo.reminders.get_todays_reminders()
    if todays:
        for r in todays:
            emoji = TYPE_EMOJI.get(r["type"], "🔔")
            done_icon = "✅" if r["done_today"] else "⏳"
            col_r, col_d = st.columns([4, 1])
            with col_r:
                st.caption(f"{emoji} {r['time']} {r['label']}")
            with col_d:
                if not r["done_today"]:
                    if st.button("✅", key=f"done_{r['id']}", help="Mark done"):
                        st.session_state.echo.reminders.mark_done(r["id"])
                        st.rerun()
                else:
                    st.caption("✅")
    else:
        st.caption("No reminders for today.")

    # Add new reminder
    with st.expander("➕ Add Reminder"):
        r_label = st.text_input("What?", placeholder="Blood pressure tablet",
                                key="r_label")
        r_type = st.selectbox("Type", ["medication", "task", "appointment"],
                              key="r_type")
        r_time = st.text_input("Time (HH:MM)", placeholder="09:00", key="r_time")
        r_days = st.multiselect(
            "Days (leave empty = daily)",
            ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"],
            key="r_days"
        )
        r_notes = st.text_input("Notes (optional)", key="r_notes")

        if st.button("Save Reminder", use_container_width=True):
            if r_label.strip() and r_time.strip():
                days = r_days if r_days else None
                st.session_state.echo.reminders.add_reminder(
                    r_label.strip(), r_type, r_time.strip(),
                    days=days, notes=r_notes.strip()
                )
                st.success(f"Added: {r_label}")
                st.rerun()
            else:
                st.warning("Please enter a name and time.")

    # Delete reminder
    all_reminders = st.session_state.echo.reminders.get_all()
    if all_reminders:
        with st.expander("🗑️ Delete Reminder"):
            options = {
                f"[{r['id']}] {r['label']} @ {r['time']}": r["id"]
                for r in all_reminders
            }
            selected = st.selectbox("Select reminder", list(options.keys()),
                                    key="del_select")
            if st.button("Delete", use_container_width=True):
                st.session_state.echo.reminders.delete_reminder(options[selected])
                st.success("Deleted.")
                st.rerun()

    st.divider()

    # Mood
    st.subheader("💭 Current Mood")
    st.markdown(
        f"### {st.session_state.current_mood_emoji} "
        f"{st.session_state.current_mood.capitalize()}"
    )
    summary = st.session_state.echo.get_mood_summary()
    if summary["total"] > 0:
        st.caption("Session mood breakdown:")
        for m, count in summary["moods"].items():
            bar = "█" * count
            st.caption(f"{MOOD_EMOJI.get(m,'?')} {m}: {bar} ({count})")

    st.divider()

    # Repeated questions
    repeated = st.session_state.echo.get_repeated_questions()
    if repeated:
        st.subheader("🔁 Repeated Questions")
        for r in repeated:
            q_short = r['question'][:35] + "..." if len(r['question']) > 35 else r['question']
            st.caption(f"• \"{q_short}\" × {r['count']}")

    st.divider()

    # Voice
    st.subheader("🔊 Voice")
    st.session_state.tts_enabled = st.toggle(
        "Speak responses aloud", value=st.session_state.tts_enabled
    )

    st.divider()

    # Session log
    st.subheader("📓 Session Log")
    if st.button("💾 Save Today's Chat", use_container_width=True):
        st.session_state.echo.save_session()
        st.success("Session saved!")

    st.divider()
    st.caption("**Stack:** Gemini 3.6 Flash · Streamlit")


#  Main chat 
st.title("🌸 EchoMemory Companion")
st.caption("A patient, caring space for your family stories.")

# Mood bar
st.markdown(
    f'<div class="mood-bar">{st.session_state.current_mood_emoji} '
    f'Feeling <strong>{st.session_state.current_mood}</strong> right now</div>',
    unsafe_allow_html=True
)

# Check for due reminders and show proactive alert
due_now = st.session_state.echo.reminders.format_due_alert()
if due_now:
    st.markdown(
        f'<div class="reminder-alert">⏰ <strong>Reminder:</strong> {due_now}</div>',
        unsafe_allow_html=True
    )

# Chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(f"{message.get('mood_emoji','')} {message['content']}")
        else:
            st.markdown(message["content"])

# Photo upload panel
if st.session_state.show_photo_upload:
    with st.container():
        st.markdown("**📷 Add a family photo**")
        uploaded_photo = st.file_uploader(
            "Choose photo", type=["jpg","jpeg","png"],
            key="photo_upload", label_visibility="collapsed"
        )
        photo_name = st.text_input("Who is this?", placeholder="e.g. Vijaya",
                                   key="photo_name")
        pcol1, pcol2 = st.columns([1, 1])
        with pcol1:
            if st.button("✅ Save", use_container_width=True):
                if uploaded_photo and photo_name.strip():
                    os.makedirs("data/photos", exist_ok=True)
                    with open(f"data/photos/{photo_name.strip()}.jpg", "wb") as f:
                        f.write(uploaded_photo.read())
                    with open("data/family_memories.txt", "a", encoding="utf-8") as f:
                        f.write(f"\n- {photo_name.strip()}'s photo is saved.")
                    st.success(f"Saved {photo_name}'s photo!")
                    st.session_state.show_photo_upload = False
                    st.rerun()
                else:
                    st.warning("Please choose a photo and enter a name.")
        with pcol2:
            if st.button("✖ Cancel", use_container_width=True):
                st.session_state.show_photo_upload = False
                st.rerun()
        st.divider()


plus_col, input_col, mic_col = st.columns([1, 10, 1])

with plus_col:
    if st.button("➕", help="Add a family photo", key="plus_btn"):
        st.session_state.show_photo_upload = not st.session_state.show_photo_upload
        st.rerun()

with input_col:
    voice_input = st.session_state.pop("voice_input", None)
    typed_input = st.chat_input("Ask about a family member...")
    prompt = (voice_input or typed_input or "").strip() or None
    

with mic_col:
    if st.button("🎤", help="Speak your question", key="mic_btn"):
        with st.spinner("🎤 Listening..."):
            spoken = listen()
        if spoken:
            st.session_state["voice_input"] = spoken
            st.rerun()
        else:
            st.error("Couldn't hear you.")

#  Handle response 
    if prompt and prompt.strip():
        result = st.session_state.echo.ask(prompt)
        mood = result["mood"]
        mood_emoji = result["mood_emoji"]

        st.session_state.messages.append({
            "role": "user", "content": prompt,
            "mood": mood, "mood_emoji": mood_emoji,
        })
        st.session_state.current_mood = mood
        st.session_state.current_mood_emoji = mood_emoji

        if result["alert_caregiver"]:
            st.markdown(
                '<div class="alert-box">⚠️ <strong>Caregiver Alert:</strong> '
                'Patient has shown signs of distress multiple times.</div>',
                unsafe_allow_html=True
            )

        with st.chat_message("user"):
            st.markdown(f"{mood_emoji} {prompt}")

        with st.chat_message("assistant"):
            with st.spinner("Remembering..."):
                response = result["answer"]
                st.markdown(response)
            if st.session_state.tts_enabled:
                speak(response)

        st.session_state.messages.append({
            "role": "assistant", "content": response,
            "mood": mood, "mood_emoji": mood_emoji,
        })

        st.rerun()