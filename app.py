import logging

import ollama
import streamlit as st

from orchestrator import Orchestrator, Turn, TurnError
from runtime import AccessDenied, AccessVerifier, Admission, CapacityError, Settings


logger = logging.getLogger("obsidian_corvids")


st.set_page_config(page_title="Obsidian Corvids", page_icon="assets/logo.png", layout="centered")


@st.cache_resource
def services():
    settings = Settings.load()
    client = ollama.Client(host=settings.ollama_host, timeout=120)
    return settings, AccessVerifier(settings), Admission(), Orchestrator(client, settings.model)

try:
    settings, access, admission, orchestrator = services()
    token = st.context.headers.get("Cf-Access-Jwt-Assertion")
    identity = access.identity(token)
except (AccessDenied, ValueError) as error:
    st.error(str(error))
    st.stop()
except Exception as error:
    logger.error("Service initialization failed: %s", type(error).__name__)
    st.error("The service is temporarily unavailable.")
    st.stop()

if st.session_state.get("identity") != identity:
    st.session_state.identity = identity
    st.session_state.chat_history = []

with st.sidebar:
    st.image("assets/logo.png", width=180)
    st.title("Obsidian Corvids")
    st.caption("Virtual C-Suite")
    if st.button("Clear conversation", icon=":material/delete_sweep:"):
        st.session_state.chat_history = []
        st.rerun()
    st.caption(f"Model: {settings.model}")

st.title("Executive Hub")
st.caption("A single orchestrator consulting CFO, CISO, CMO and COO data tools.")
st.warning(
    "DEMO DATA ONLY. All metrics are fixed examples, not live business, security, "
    "audit, or compliance information. Do not use for business decisions."
)
if settings.environment == "development":
    st.info("Development mode has no authentication. Never publish this mode to the internet.")

for turn in st.session_state.chat_history:
    with st.chat_message("user"):
        st.markdown(turn.query)
    with st.chat_message("assistant"):
        st.markdown(turn.answer)

if query := st.chat_input("Ask about the simulated executive metrics", max_chars=2000):
    try:
        with admission.admit(identity):
            with st.spinner("Consulting the executive tools..."):
                updated_history = orchestrator.run(query, st.session_state.chat_history)
        completed_turn: Turn = updated_history[-1]
        st.session_state.chat_history = updated_history
        with st.chat_message("user"):
            st.markdown(completed_turn.query)
        with st.chat_message("assistant"):
            st.markdown(completed_turn.answer)
    except (CapacityError, TurnError) as error:
        st.error(str(error))
    except Exception as error:
        logger.error("Chat request failed: %s", type(error).__name__)
        st.error("The request could not be completed. Please try again later.")