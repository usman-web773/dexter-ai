"""
Dextor AI — Streamlit Agent
============================
A production-ready Streamlit app powering a custom AI agent called "Dextor AI",
backed by the Anthropic Claude API.

Features
--------
1. Anthropic Claude backend (model configurable, defaults to Claude Sonnet).
2. Dark / red "Dextor AI" branded UI.
3. Voice input (browser speech-to-text) + text-to-speech playback of replies.
4. A simulated audio/video "call" screen with live camera/mic preview.
5. Google Sheets logging of every chat turn via gspread + a service account.
6. Defensive error handling everywhere external services are touched, so a
   missing API key or broken Sheets connection never crashes the app.

Deploy: push this file + requirements.txt to a GitHub repo and point
Streamlit Community Cloud at it. No secrets are hard-coded — the user
supplies their own Anthropic key and (optionally) a Google service-account
JSON at runtime via the sidebar.
"""

import json
import time
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

# --- Optional dependencies -------------------------------------------------
# We import these defensively. If a package is missing or fails to import,
# the corresponding feature is disabled instead of crashing the whole app.

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

try:
    from streamlit_mic_recorder import speech_to_text
    MIC_AVAILABLE = True
except ImportError:
    MIC_AVAILABLE = False


# =============================================================================
# PAGE CONFIG + THEME
# =============================================================================

st.set_page_config(
    page_title="Dextor AI",
    page_icon="🔺",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEXTOR_CSS = """
<style>
:root {
    --dextor-bg: #0b0b0b;
    --dextor-bg-alt: #141414;
    --dextor-red: #ff0033;
    --dextor-red-dim: #7a0019;
    --dextor-text: #f2f2f2;
    --dextor-muted: #9a9a9a;
}

/* App background */
.stApp {
    background: radial-gradient(circle at 20% 0%, #1a0006 0%, var(--dextor-bg) 45%);
    color: var(--dextor-text);
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #120000 0%, var(--dextor-bg) 100%);
    border-right: 1px solid var(--dextor-red-dim);
}

/* Headings */
h1, h2, h3 {
    color: var(--dextor-text) !important;
    letter-spacing: 0.5px;
}

/* Dextor brand title */
.dextor-title {
    font-size: 2.4rem;
    font-weight: 800;
    color: var(--dextor-text);
    text-shadow: 0 0 18px var(--dextor-red);
    margin-bottom: 0;
}
.dextor-title span { color: var(--dextor-red); }

.dextor-subtitle {
    color: var(--dextor-muted);
    font-size: 0.95rem;
    margin-top: -8px;
    margin-bottom: 1.2rem;
}

/* Buttons */
.stButton > button, .stDownloadButton > button {
    background: linear-gradient(135deg, var(--dextor-red), #990022);
    color: #fff;
    border: 1px solid var(--dextor-red);
    border-radius: 8px;
    font-weight: 600;
    box-shadow: 0 0 12px rgba(255,0,51,0.25);
    transition: all 0.15s ease-in-out;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    box-shadow: 0 0 22px rgba(255,0,51,0.55);
    transform: translateY(-1px);
    border-color: #fff;
}

/* Chat bubbles */
[data-testid="stChatMessage"] {
    background: var(--dextor-bg-alt);
    border: 1px solid #2a0008;
    border-radius: 12px;
    padding: 4px;
}

/* Inputs */
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
    background-color: #161616 !important;
    color: var(--dextor-text) !important;
    border: 1px solid var(--dextor-red-dim) !important;
    border-radius: 8px !important;
}

/* Tabs */
button[data-baseweb="tab"] {
    color: var(--dextor-muted);
    font-weight: 600;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--dextor-red) !important;
    border-bottom: 2px solid var(--dextor-red) !important;
}

/* Status pills */
.dextor-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.4px;
}
.pill-ok { background: rgba(0,200,90,0.15); color: #2ecc71; border: 1px solid #2ecc71; }
.pill-bad { background: rgba(255,0,51,0.15); color: var(--dextor-red); border: 1px solid var(--dextor-red); }
.pill-warn { background: rgba(255,200,0,0.12); color: #e6b800; border: 1px solid #e6b800; }

hr { border-color: var(--dextor-red-dim) !important; }
</style>
"""
st.markdown(DEXTOR_CSS, unsafe_allow_html=True)


# =============================================================================
# SESSION STATE
# =============================================================================

def init_state():
    defaults = {
        "messages": [],              # chat history: [{"role": "...", "content": "..."}]
        "anthropic_client": None,
        "gs_client": None,
        "gs_sheet": None,
        "gs_status": "disconnected",  # disconnected | connected | error
        "gs_error": "",
        "tts_enabled": True,
        "model_name": "claude-sonnet-5",
        "system_prompt": (
            "You are Dextor AI, a sharp, confident, no-nonsense AI assistant. "
            "Keep answers useful and to the point, with a slightly bold, "
            "futuristic tone that matches your black-and-red interface."
        ),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_anthropic_client(api_key: str):
    """Build (or reuse) an Anthropic client. Never raises — returns None on failure."""
    if not api_key:
        return None
    if not ANTHROPIC_AVAILABLE:
        st.sidebar.error("The `anthropic` package is not installed in this environment.")
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        return client
    except Exception as e:  # noqa: BLE001 - surface any init error to the user, don't crash
        st.sidebar.error(f"Could not initialize Anthropic client: {e}")
        return None


def ask_dextor(client, model: str, system_prompt: str, history: list) -> str:
    """Send the conversation to Claude and return the assistant's reply text.
    Returns a friendly error string instead of raising, so the UI never crashes.
    """
    if client is None:
        return "⚠️ Dextor AI is offline — add a valid Anthropic API key in the sidebar."
    try:
        api_messages = [{"role": m["role"], "content": m["content"]} for m in history]
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=api_messages,
        )
        # Concatenate all text blocks in the response
        text_parts = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        return "".join(text_parts) if text_parts else "(Dextor AI returned an empty response.)"
    except anthropic.APIStatusError as e:  # type: ignore[attr-defined]
        return f"⚠️ Claude API error ({e.status_code}): {e.message}"
    except Exception as e:  # noqa: BLE001
        return f"⚠️ Unexpected error talking to Dextor AI: {e}"


def connect_google_sheet(service_account_json: dict, sheet_key_or_url: str):
    """Authorize gspread with a service account and open the target sheet.
    Returns (client, sheet, error_message). Never raises.
    """
    if not GSPREAD_AVAILABLE:
        return None, None, "gspread / google-auth packages are not installed."
    if not service_account_json or not sheet_key_or_url:
        return None, None, "Missing service account JSON or sheet URL/key."
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(service_account_json, scopes=scopes)
        gc = gspread.authorize(creds)

        if sheet_key_or_url.startswith("http"):
            sheet = gc.open_by_url(sheet_key_or_url).sheet1
        else:
            sheet = gc.open_by_key(sheet_key_or_url).sheet1

        # Ensure header row exists
        existing = sheet.get_all_values()
        if not existing:
            sheet.append_row(["timestamp", "role", "content"])

        return gc, sheet, ""
    except Exception as e:  # noqa: BLE001
        return None, None, str(e)


def log_to_sheet(sheet, role: str, content: str):
    """Append one chat turn to the connected Google Sheet. Silently no-ops on failure
    (surfaces a small toast) so a Sheets outage never breaks the chat experience.
    """
    if sheet is None:
        return
    try:
        sheet.append_row([datetime.utcnow().isoformat(), role, content])
    except Exception as e:  # noqa: BLE001
        st.toast(f"⚠️ Could not log to Google Sheet: {e}", icon="⚠️")


def speak_text(text: str, key: str):
    """Speak `text` aloud in the browser using the Web Speech API (client-side TTS,
    no external service / API cost)."""
    if not text:
        return
    safe_text = json.dumps(text)
    components.html(
        f"""
        <script>
        const msg = new SpeechSynthesisUtterance({safe_text});
        msg.rate = 1.0;
        msg.pitch = 0.9;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(msg);
        </script>
        """,
        height=0,
        width=0,
    )


def render_call_widget(status_text: str):
    """Render the simulated audio/video call screen (local camera/mic preview
    via getUserMedia). Pure front-end simulation — no signaling server required."""
    components.html(
        f"""
        <div style="
            background:#0b0b0b;border:1px solid #7a0019;border-radius:16px;
            padding:24px;text-align:center;font-family:sans-serif;color:#f2f2f2;">
          <div style="
              width:110px;height:110px;border-radius:50%;margin:0 auto 14px auto;
              background:radial-gradient(circle, #ff0033 0%, #330008 80%);
              display:flex;align-items:center;justify-content:center;
              box-shadow:0 0 30px rgba(255,0,51,0.6);
              font-size:38px;font-weight:800;">D</div>
          <div style="font-size:1.3rem;font-weight:700;">Dextor AI</div>
          <div style="color:#e6b800;margin-bottom:14px;">{status_text}</div>
          <video id="dextorLocalVideo" autoplay muted playsinline
                 style="width:260px;border-radius:12px;border:1px solid #ff0033;background:#111;"></video>
          <div id="dextorCallErr" style="color:#ff5566;font-size:0.8rem;margin-top:8px;"></div>
        </div>
        <script>
        (async () => {{
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{ video: true, audio: true }});
                document.getElementById('dextorLocalVideo').srcObject = stream;
            }} catch (err) {{
                document.getElementById('dextorCallErr').innerText =
                    "Camera/mic not available: " + err.message;
            }}
        }})();
        </script>
        """,
        height=420,
    )


# =============================================================================
# SIDEBAR — CONFIGURATION
# =============================================================================

with st.sidebar:
    st.markdown("### 🔺 Dextor AI Config")

    api_key = st.text_input(
        "Anthropic Claude API Key",
        type="password",
        help="Your key is only kept in this session's memory — never written to disk.",
    )
    st.session_state.model_name = st.selectbox(
        "Model",
        ["claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5-20251001"],
        index=0,
    )

    if api_key:
        st.session_state.anthropic_client = get_anthropic_client(api_key)
        if st.session_state.anthropic_client:
            st.markdown('<span class="dextor-pill pill-ok">CLAUDE CONNECTED</span>', unsafe_allow_html=True)
    else:
        st.session_state.anthropic_client = None
        st.markdown('<span class="dextor-pill pill-warn">NO API KEY</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🔊 Voice")
    st.session_state.tts_enabled = st.checkbox("Speak Dextor's replies aloud", value=True)
    if not MIC_AVAILABLE:
        st.caption("Voice **input** needs the `streamlit-mic-recorder` package "
                   "(see requirements.txt). Text chat still works without it.")

    st.markdown("---")
    st.markdown("### 📊 Google Sheets Logging")
    sa_file = st.file_uploader("Service account JSON", type=["json"])
    sheet_ref = st.text_input("Sheet URL or Key")
    if st.button("Connect Sheet", use_container_width=True):
        if sa_file is None or not sheet_ref:
            st.warning("Upload a service-account JSON and provide a sheet URL/key first.")
        else:
            try:
                sa_json = json.loads(sa_file.getvalue().decode("utf-8"))
            except Exception as e:  # noqa: BLE001
                sa_json = None
                st.error(f"Invalid service account JSON: {e}")

            if sa_json:
                gc, sheet, err = connect_google_sheet(sa_json, sheet_ref)
                if err:
                    st.session_state.gs_status = "error"
                    st.session_state.gs_error = err
                else:
                    st.session_state.gs_client = gc
                    st.session_state.gs_sheet = sheet
                    st.session_state.gs_status = "connected"
                    st.session_state.gs_error = ""

    if st.session_state.gs_status == "connected":
        st.markdown('<span class="dextor-pill pill-ok">SHEET CONNECTED</span>', unsafe_allow_html=True)
    elif st.session_state.gs_status == "error":
        st.markdown('<span class="dextor-pill pill-bad">SHEET ERROR</span>', unsafe_allow_html=True)
        st.caption(st.session_state.gs_error)
    else:
        st.markdown('<span class="dextor-pill pill-warn">SHEET NOT CONNECTED</span>', unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🗑️ Clear chat history", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# =============================================================================
# MAIN HEADER
# =============================================================================

st.markdown('<div class="dextor-title">DEXTOR <span>AI</span></div>', unsafe_allow_html=True)
st.markdown('<div class="dextor-subtitle">Your black-and-red command center — chat, call, and log, all in one place.</div>', unsafe_allow_html=True)

tab_chat, tab_call, tab_logs = st.tabs(["💬 Chat", "📞 Voice / Video Call", "🗂️ Logs"])


# =============================================================================
# TAB 1 — CHAT
# =============================================================================

with tab_chat:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    voice_text = None
    if MIC_AVAILABLE:
        st.caption("🎙️ Tap to speak, or just type below.")
        voice_text = speech_to_text(
            language="en",
            start_prompt="🎙️ Start voice input",
            stop_prompt="⏹️ Stop",
            just_once=True,
            use_container_width=True,
            key="chat_stt",
        )

    typed_text = st.chat_input("Message Dextor AI...")
    user_input = voice_text or typed_text

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        log_to_sheet(st.session_state.gs_sheet, "user", user_input)
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Dextor AI is thinking..."):
                reply = ask_dextor(
                    st.session_state.anthropic_client,
                    st.session_state.model_name,
                    st.session_state.system_prompt,
                    st.session_state.messages,
                )
            st.markdown(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})
        log_to_sheet(st.session_state.gs_sheet, "assistant", reply)

        if st.session_state.tts_enabled:
            speak_text(reply, key=f"tts_{len(st.session_state.messages)}")


# =============================================================================
# TAB 2 — SIMULATED VOICE / VIDEO CALL
# =============================================================================

with tab_call:
    st.markdown("#### Live call with Dextor AI")
    st.caption(
        "This simulates a real-time call experience using your browser's camera/mic "
        "preview, speech-to-text, and text-to-speech — powered by the same Claude "
        "backend as the chat tab. No third-party video infrastructure required."
    )

    col1, col2 = st.columns([1.1, 1])
    with col1:
        render_call_widget("● Connected" if st.session_state.anthropic_client else "○ Waiting for API key")

    with col2:
        st.markdown("##### Captions")
        caption_box = st.container(height=260, border=True)

        if MIC_AVAILABLE:
            call_text = speech_to_text(
                language="en",
                start_prompt="🎙️ Speak to Dextor",
                stop_prompt="⏹️ Stop",
                just_once=True,
                use_container_width=True,
                key="call_stt",
            )
        else:
            call_text = st.text_input("Say something to Dextor (type since mic package isn't installed):", key="call_fallback")

        if call_text:
            caption_box.markdown(f"**You:** {call_text}")
            with st.spinner("Dextor AI is responding..."):
                call_history = st.session_state.messages + [{"role": "user", "content": call_text}]
                reply = ask_dextor(
                    st.session_state.anthropic_client,
                    st.session_state.model_name,
                    st.session_state.system_prompt,
                    call_history,
                )
            caption_box.markdown(f"**Dextor AI:** {reply}")

            st.session_state.messages.append({"role": "user", "content": call_text})
            st.session_state.messages.append({"role": "assistant", "content": reply})
            log_to_sheet(st.session_state.gs_sheet, "user", call_text)
            log_to_sheet(st.session_state.gs_sheet, "assistant", reply)

            if st.session_state.tts_enabled:
                speak_text(reply, key="call_tts")


# =============================================================================
# TAB 3 — LOGS
# =============================================================================

with tab_logs:
    st.markdown("#### Session chat log")
    if st.session_state.messages:
        st.dataframe(
            [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
            use_container_width=True,
        )
    else:
        st.info("No messages yet this session.")

    st.markdown("#### Google Sheet log")
    if st.session_state.gs_status == "connected" and st.session_state.gs_sheet is not None:
        try:
            records = st.session_state.gs_sheet.get_all_values()
            if records:
                st.dataframe(records[1:], use_container_width=True) if len(records) > 1 else st.info("Sheet is empty aside from the header row.")
            else:
                st.info("Sheet is empty.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read from Google Sheet: {e}")
    else:
        st.info("Connect a Google Sheet from the sidebar to see synced logs here.")
