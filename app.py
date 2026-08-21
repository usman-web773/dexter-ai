import openai
import streamlit as st

st.set_page_config(page_title="Dextor AI", page_icon="🤖")

st.title("🤖 Dextor AI")
st.write("Aapka apna intelligent assistant!")

st.sidebar.title("Settings")
api_key = st.sidebar.text_input("OpenAI API Key", type="password")

if not api_key:
  st.warning("Baraye meharbani sidebar mein apni OpenAI API key enter karein.")
else:
  client = openai.OpenAI(api_key=api_key)

  if "messages" not in st.session_state:
    st.session_state.messages = []

  for message in st.session_state.messages:
    with st.chat_message(message["role"]):
      st.markdown(message["content"])

  if prompt := st.chat_input("Dextor se kuch bhi poochein..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
      st.markdown(prompt)

    with st.chat_message("assistant"):
      with st.spinner("Soch raha hai..."):
        try:
          response = client.chat.completions.create(
              model="gpt-4o-mini",
              messages=[{"role": "user", "content": prompt}],
          )
          bot_reply = response.choices[0].message.content
        except Exception as e:
          bot_reply = f"Error aa gaya: {e}"

        st.markdown(bot_reply)
        st.session_state.messages.append(
            {"role": "assistant", "content": bot_reply}
        )
