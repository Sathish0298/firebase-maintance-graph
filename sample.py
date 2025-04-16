import streamlit as st
import os
import time
import uuid
import faiss
import numpy as np
import firebase_admin
import markdown
import requests
import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv
from firebase_admin import credentials, db
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.documents import Document

# -------------------- Sidebar Menu --------------------
st.set_page_config(page_title="Motor Dashboard", layout="wide")
st.sidebar.title("🔧 Menu")
selected_view = st.sidebar.radio("Go to", ["📈 Graph View", "🤖 Predictive Analysis"])

# -------------------- Firebase Init (One time) --------------------
if not firebase_admin._apps:
    cred = credentials.Certificate('predictive-18aaa-firebase-adminsdk-fbsvc-b0406bda70.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://predictive-18aaa-default-rtdb.firebaseio.com/'
    })

ref = db.reference('sensor_data')

# -------------------- GRAPH VIEW --------------------
def graph_view():
    st.title("📊 Real-Time Sensor Data Visualization")

    def get_sensor_data():
        data = ref.get()
        if not data:
            return pd.DataFrame()
        records = list(data.values())[-40:]
        df = pd.DataFrame(records)
        df.rename(columns={"Temperature": "temperature", "VibrationLevel": "vibration", 
                           "Current": "current", "Humidity": "humidity", "timestamp": "timestamp"}, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values(by="timestamp")
        return df

    df = get_sensor_data()

    if df.empty:
        st.warning("No data available yet!")
        return

    df["timestamp_str"] = df["timestamp"].dt.strftime("%H:%M:%S")

    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df["timestamp_str"], y=df["temperature"], mode="lines+markers", name="Temperature (°C)", line=dict(color="red", width=2)))
    fig1.add_trace(go.Scatter(x=df["timestamp_str"], y=df["vibration"], mode="lines+markers", name="Vibration Level", line=dict(color="blue", width=2)))
    fig1.update_layout(title="Temperature & Vibration Over Time", xaxis_title="Time", yaxis_title="Value", xaxis=dict(tickangle=-45), yaxis=dict(showgrid=True))

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df["timestamp_str"], y=df["current"], mode="lines+markers", name="Current (A)", line=dict(color="green", width=2)))
    fig2.add_trace(go.Scatter(x=df["timestamp_str"], y=df["humidity"], mode="lines+markers", name="Humidity (%)", line=dict(color="purple", width=2)))
    fig2.update_layout(title="Current & Humidity Over Time", xaxis_title="Time", yaxis_title="Value", xaxis=dict(tickangle=-45), yaxis=dict(showgrid=True))

    st.plotly_chart(fig1, use_container_width=True)
    st.plotly_chart(fig2, use_container_width=True)

# -------------------- ANALYSIS VIEW --------------------
def analysis_view():
    load_dotenv()
    EMAIL_SENDER = os.getenv("EMAIL_SENDER")
    EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
    BREVO_API_KEY = os.getenv("BREVO_API_KEY")

    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
    index = faiss.IndexFlatL2(len(embeddings.embed_query("hello world")))
    vector_store = FAISS(
        embedding_function=embeddings,
        index=index,
        docstore=InMemoryDocstore(),
        index_to_docstore_id={},
    )
    model = ChatOpenAI(model="gpt-4o", temperature=0)

    if "response" not in st.session_state:
        st.session_state.response = "Waiting for sensor data..."

    def send_alert_email(subject, message):
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        }
        payload = {
            "sender": {"name": "Predictive AI", "email": EMAIL_SENDER},
            "to": [{"email": EMAIL_RECEIVER, "name": "User"}],
            "subject": subject,
            "htmlContent": f"<p>{message}</p>"
        }
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 201:
            print("🔔 Alert Email Sent Successfully!")
        else:
            print(f"❌ Failed to send email: {response.text}")

    def monitor_sensor_data():
        sensor_data = ref.order_by_child("timestamp").limit_to_last(1).get()
        if sensor_data:
            latest_entry = list(sensor_data.values())[0]
            sensor_text = f"Timestamp: {latest_entry['timestamp']}, Current: {latest_entry['Current']}A, Temp: {latest_entry['Temperature']}°C, Vibration: {latest_entry['VibrationLevel']}, Humidity: {latest_entry['Humidity']}%"

            doc_id = str(uuid.uuid4())
            doc = Document(page_content=sensor_text)
            vector_store.docstore.add({doc_id: doc})
            vector_store.index_to_docstore_id[len(vector_store.index_to_docstore_id)] = doc_id
            vector_store.add_texts([sensor_text])

            query = "High vibration detected, find similar past cases"
            retrieved_docs = vector_store.similarity_search(query, k=3)
            retrieved_text = "\n".join([doc.page_content for doc in retrieved_docs]) if retrieved_docs else "No relevant past data found."

            prompt = ChatPromptTemplate([
                ("system", "You are an AI specializing in predictive maintenance for a 5V DC motor."),
                ("user", f"""
                !Important - always make sure the output is a neat and beautiful Markdown.             
                New Sensor Data: {sensor_text}
                
                🔍 Relevant Historical Data:
                {retrieved_text}

                ### Questions:
                - Are current trends normal?
                - What failures might occur?
                - Also make sure to check the motor's health and performance.
                - If there is only any important issue or risk for motor's health/performance, what maintenance actions should be taken?
                """)
            ])

            llm_chain = prompt | model | StrOutputParser()
            output = llm_chain.invoke({"retrieved_text": retrieved_text})
            st.session_state.response = output

            if "critical" in output.lower() or "urgent" in output.lower() or "high risk" in output.lower():
                send_alert_email("⚠️ Critical Motor Issue Detected!", output)
        else:
            st.warning("No new sensor data found.")

    st.title("🤖 Predictive Maintenance Analysis")
    if st.button("🔄 Run Analysis Now"):
        monitor_sensor_data()
    st.markdown(st.session_state.response, unsafe_allow_html=True)
    st.info("Click refresh above to re-analyze the latest data.")

# -------------------- Main Render Logic --------------------
if selected_view == "📈 Graph View":
    graph_view()
elif selected_view == "🤖 Predictive Analysis":
    analysis_view()
