import requests
import streamlit as st

st.set_page_config(page_title="Dextor AI", page_icon="🤖")

st.title("🤖 Dextor AI")
st.write("Aapka apna intelligent assistant!")

# Session state yaad rakhne ke liye ke pehle kya baat hui
if "messages" not in st.session_state:
  st.session_state.messages = []

# Purani chat screen par dikhane ke liye
for message in st.session_state.messages:
  with st.chat_message(message["role"]):
    st.markdown(message["content"])

# Naya message likhne ki jagah
if prompt := st.chat_input("Dextor se kuch bhi poochein..."):
  # User ka message add karo
  st.session_state.messages.append({"role": "user", "content": prompt})
  with st.chat_message("user"):
    st.markdown(prompt)

  # n8n webhook par request bhejna
  with st.chat_message("assistant"):
    with st.spinner("Soch raha hai..."):
      try:
        # Apna n8n production webhook URL yahan dalein
        webhook_url = "https://usmanmehboob76.app.n8n.cloud/webhook/chat"

        payload = {"chatInput": prompt, "sessionId": "user-1"}

        response = requests.post(webhook_url, json=payload)

        if response.status_code == 200:
          data = response.json()
          # Check karein ke n8n se kya key aa rahi hai (output, text, reply, etc.)
          bot_reply = (
              data.get("output")
              or data.get("text")
              or data.get("reply")
              or str(data)
          )
        else:
          bot_reply = "Oops! n8n se connection mein masla aa gaya."

        st.markdown(bot_reply)
        st.session_state.messages.append(
            {"role": "assistant", "content": bot_reply}
        )

      except Exception as e:
        st.error(f"Error aa gaya: {e}")
