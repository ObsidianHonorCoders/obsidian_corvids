import streamlit as st
import ollama
from tools import AVAILABLE_TOOLS

# Map function names to actual callables for execution
tool_map = {fn.__name__: fn for fn in AVAILABLE_TOOLS}

st.set_page_config(
    page_title="Obsidian Corvids - Virtual C-Suite Hub",
    page_icon="assets/logo.png",
    layout="centered")

st.title("🐦‍⬛ Obsidian Corvids \n Virtual C-Suite Executive Hub")
st.caption("Powered locally by Ollama (Llama 3.2) & Multi-Agent Tool Calling")

# Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "You are the Executive Orchestrator for the Virtual C-Suite. "
                "Analyze user questions regarding finance, security, marketing, or operations, "
                "and call the appropriate C-suite expert tool (CFO, CISO, CMO, COO) before "
                "synthesizing a professional executive answer."
            )
        }
    ]

# Display prior chat messages (ignoring the system prompt)
for message in st.session_state.messages:
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            if message.get("content"):
                st.markdown(message["content"])

# User input via chat bar
if user_query := st.chat_input("Ask the C-Suite (e.g., 'How is our cash flow and security posture?')..."):
    # Append user message
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    # Generate response with Ollama
    with st.chat_message("assistant"):
        with st.spinner("Consulting C-Suite Executives..."):
            try:
                # First chat call to check for tool calls
                response = ollama.chat(
                    model='llama3.2',
                    messages=st.session_state.messages,
                    tools=AVAILABLE_TOOLS
                )

                # Append assistant message to history
                st.session_state.messages.append(response.message)

                # Handle tool execution if requested by the model
                if response.message.get("tool_calls"):
                    for tool_call in response.message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = tool_call.function.arguments

                        with st.expander(f"🛠️ Executing Tool: `{function_name}`"):
                            st.write(f"Arguments: {function_args}")
                            
                            if function_name in tool_map:
                                tool_output = tool_map[function_name](**function_args)
                            else:
                                tool_output = '{"error": "Tool not found"}'
                            
                            st.json(tool_output)

                        # Append tool result back to messages
                        st.session_state.messages.append({
                            'role': 'tool',
                            'tool_name': function_name,
                            'content': str(tool_output)
                        })

                    # Second chat call to synthesize final answer using tool outputs
                    final_response = ollama.chat(
                        model='llama3.2',
                        messages=st.session_state.messages
                    )
                    st.session_state.messages.append(final_response.message)
                    st.markdown(final_response.message.content)
                else:
                    # Direct response if no tool was needed
                    if response.message.get("content"):
                        st.markdown(response.message.content)

            except Exception as e:
                st.error(f"Error connecting to local Ollama instance: {e}")
                st.info("Make sure Ollama is running (`ollama serve`) and you have pulled the model (`ollama pull llama3.2`).")