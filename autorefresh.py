import os
import time
import uuid
import faiss
import numpy as np
import firebase_admin
import markdown
import threading
import requests
from dotenv import load_dotenv
from flask import Flask, render_template_string, jsonify
from firebase_admin import credentials, db
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.documents import Document  # ✅ Fix: Ensure documents are stored correctly

# Load environment variables
load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

print("ENV Variables Loaded")

# Initialize Flask
app = Flask(__name__)

# Connect Firebase Realtime Database
cred = credentials.Certificate('predictive-18aaa-firebase-adminsdk-fbsvc-b0406bda70.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://predictive-18aaa-default-rtdb.firebaseio.com/sensor_data.json'
})
ref = db.reference('sensor_data')

print("Firebase Connected")

# Initialize FAISS
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
index = faiss.IndexFlatL2(len(embeddings.embed_query("hello world")))
vector_store = FAISS(
    embedding_function=embeddings,
    index=index,
    docstore=InMemoryDocstore(),
    index_to_docstore_id={},
)

print("FAISS Datastore Initialized")

# LLM Model
model = ChatOpenAI(model="gpt-4o", temperature=0)

# Global response variable
response = "Waiting for sensor data..."

# Function to send alert email via Brevo
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

# Function to monitor sensor data in real-time
def monitor_sensor_data():
    global response
    while True:
        sensor_data = ref.order_by_child("timestamp").limit_to_last(1).get()

        if sensor_data:
            latest_entry = list(sensor_data.values())[0]
            sensor_text = f"Timestamp: {latest_entry['timestamp']}, Current: {latest_entry['Current']}A, Temp: {latest_entry['Temperature']}°C, Vibration: {latest_entry['VibrationLevel']}, Humidity: {latest_entry['Humidity']}%"
            
            # Store sensor data correctly
            doc_id = str(uuid.uuid4())
            doc = Document(page_content=sensor_text)  # ✅ Fix
            vector_store.docstore.add({doc_id: doc})  # ✅ Fix
            vector_store.index_to_docstore_id[len(vector_store.index_to_docstore_id)] = doc_id
            vector_store.add_texts([sensor_text])
            print("Stored data:", vector_store.docstore._dict)
            print(f"New Sensor Data: {sensor_text}")

            # Retrieve relevant past cases
            query = "High vibration detected, find similar past cases"
            retrieved_docs = vector_store.similarity_search(query, k=3)
            retrieved_text = "\n".join([doc.page_content for doc in retrieved_docs]) if retrieved_docs else "No relevant past data found."

            print(f"Retrieved Data: {retrieved_text}")

            # Predictive Maintenance Analysis using LLM
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
            response = llm_chain.invoke({"retrieved_text": retrieved_text})
            
            # Check if alert needs to be sent
            if "critical" in response.lower() or "urgent" in response.lower() or "high risk" in response.lower():
                send_alert_email("⚠️ Critical Motor Issue Detected!", response)

        else:
            print("No new sensor data available.")

        time.sleep()  # ✅ Auto-refresh every 1 minute

# Start monitoring sensor data in a separate thread
threading.Thread(target=monitor_sensor_data, daemon=True).start()

@app.route('/')
def home():
    html_content = markdown.markdown(response)
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sensor Data Analysis</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { padding: 20px; font-family: Arial, sans-serif; }
            .container { max-width: 800px; margin: auto; background: #f8f9fa; padding: 20px; border-radius: 10px; }
            h2, h3 { color: #007bff; }
            strong { color: #343a40; }
        </style>
        <script>
            setInterval(function() {
                fetch('/update').then(response => response.json()).then(data => {
                    document.getElementById("response").innerHTML = data.content;
                });
            }, 60000);  // ✅ Refresh every 60 seconds
        </script>
    </head>
    <body>
        <div class="container">
            <h2 class="text-center">Sensor Data Analysis</h2>
            <hr>
            <div id="response">{{ content|safe }}</div>
        </div>
    </body>
    </html>
    """, content=html_content)

@app.route('/update')
def update():
    return jsonify({"content": markdown.markdown(response)})


if __name__ == '__main__':
    print("🚀 Starting Flask server...")
    app.run(debug=True, use_reloader=False, port=5001)

