import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import firebase_admin
from firebase_admin import credentials, db
import time

# Firebase Initialization (Only initialize once)
if not firebase_admin._apps:
    cred = credentials.Certificate("predictive-18aaa-firebase-adminsdk-fbsvc-b0406bda70.json")  # Replace with actual path
    firebase_admin.initialize_app(cred, {"databaseURL": "https://predictive-18aaa-default-rtdb.firebaseio.com/"})  # Replace with actual URL

def get_sensor_data():
    """Fetch the last 50 sensor data records from Firebase and format them into a DataFrame."""
    ref = db.reference("sensor_data")  
    data = ref.get()
    
    if not data:
        return pd.DataFrame()

    records = list(data.values())[-40:]  # Fetch the last 50 records

    df = pd.DataFrame(records)

    # Rename columns for consistency
    df.rename(columns={"Temperature": "temperature", "VibrationLevel": "vibration", 
                       "Current": "current", "Humidity": "humidity", "timestamp": "timestamp"}, inplace=True)

    # Convert timestamp to datetime format
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Sort by timestamp
    df = df.sort_values(by="timestamp")

    return df

def update_chart():
    """Fetch data and plot real-time graphs."""
    st.title("📊 Real-Time Sensor Data Visualization")

    df = get_sensor_data()

    if df.empty:
        st.warning("No data available yet!")
        return

    # Convert timestamps to string format for better visualization
    df["timestamp_str"] = df["timestamp"].dt.strftime("%H:%M:%S")  # Display only time for better readability

    # Plot 1: Temperature & Vibration
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df["timestamp_str"], y=df["temperature"], mode="lines+markers", name="Temperature (°C)", line=dict(color="red", width=2)))
    fig1.add_trace(go.Scatter(x=df["timestamp_str"], y=df["vibration"], mode="lines+markers", name="Vibration Level", line=dict(color="blue", width=2)))
    fig1.update_layout(title="Temperature & Vibration Over Time", xaxis_title="Time", yaxis_title="Value", xaxis=dict(tickangle=-45), yaxis=dict(showgrid=True))

    # Plot 2: Current & Humidity
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df["timestamp_str"], y=df["current"], mode="lines+markers", name="Current (A)", line=dict(color="green", width=2)))
    fig2.add_trace(go.Scatter(x=df["timestamp_str"], y=df["humidity"], mode="lines+markers", name="Humidity (%)", line=dict(color="purple", width=2)))
    fig2.update_layout(title="Current & Humidity Over Time", xaxis_title="Time", yaxis_title="Value", xaxis=dict(tickangle=-45), yaxis=dict(showgrid=True))

    # Display graphs
    st.plotly_chart(fig1, use_container_width=True)
    st.plotly_chart(fig2, use_container_width=True)

# Auto-refresh logic using Streamlit's built-in autorefresh
st.experimental_set_query_params(refresh_time=int(time.time()))

update_chart()

# Auto-refresh every 2 seconds
time.sleep(2)
st.rerun()
