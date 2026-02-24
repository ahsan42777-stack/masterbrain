import os
import time
import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part

# ==========================================
# SECRET KEY INJECTION (NEW)
# ==========================================
# This writes your secret JSON file temporarily so Google Cloud can read it
if "GCP_SA_KEY" in st.secrets:
    with open("gcp_key.json", "w") as f:
        f.write(st.secrets["GCP_SA_KEY"])
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp_key.json"

# ==========================================
# CONFIGURATION
# ==========================================
PROJECT_ID = "project-1a334c02-70f6-4b1c-987"
REGION = "us-east1" 
TUNED_ENDPOINT_ID = "projects/459138550386/locations/us-east1/endpoints/8842556184574558208"

SYSTEM_INSTRUCTION = """
You are a senior quantitative analyst and algorithmic trading engine. 
You strictly adhere to the IFX "FDM" (Four-Dimensional Matrix) framework.
FDM Pillars:
1. Levels (Pivots, S/R Flips)
2. Market Structure (BOS, SMS)
3. Time (Sessions, volume periods, time-of-day constraints)
4. Dimensional Alignment (MTF / Multi-Time Frame context).
Output your analysis strictly in JSON format.
""".strip()

# ==========================================
# STREAMLIT UI SETUP
# ==========================================
st.set_page_config(page_title="IFX Master Brain", page_icon="🧠", layout="centered")

st.title("🧠 IFX Master Brain")
st.subheader("Mobile FDM Chart Analyzer")
st.markdown("Upload a screenshot from your gallery to generate instant FDM analysis.")

# Mobile-friendly file uploader
uploaded_file = st.file_uploader("Choose a chart screenshot...", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    st.image(uploaded_file, caption="Chart Ready for Analysis", use_container_width=True)
    
    if st.button("Run FDM Analysis 🚀", type="primary"):
        with st.spinner("Master Brain is analyzing the matrix..."):
            try:
                vertexai.init(project=PROJECT_ID, location=REGION)
                master_brain = GenerativeModel(
                    model_name=TUNED_ENDPOINT_ID,
                    system_instruction=SYSTEM_INSTRUCTION
                )
                
                image_bytes = uploaded_file.getvalue()
                image_part = Part.from_data(data=image_bytes, mime_type=uploaded_file.type)
                
                brain_prompt = """
                Analyze this live chart based on FDM. 
                Identify the Asset, current Market Structure, and key Levels.
                
                IMPORTANT: Output your standard FDM analysis, but your final key MUST be 
                "trade_summary" formatted exactly like this JSON structure:
                
                "trade_summary": {
                  "Bias": "[Overall Direction]",
                  "Levels": [
                    {"Level Type": "Pivot Point", "Price Point": "[Price]", "Condition / Notes": "[Condition]"},
                    {"Level Type": "Target 1", "Price Point": "[Price]", "Condition / Notes": "[Condition]"},
                    {"Level Type": "Target 2", "Price Point": "[Price]", "Condition / Notes": "[Condition]"},
                    {"Level Type": "Invalidation", "Price Point": "[Price]", "Condition / Notes": "[Condition]"}
                  ]
                }
                """
                
                final_response = master_brain.generate_content([brain_prompt, image_part])
                
                st.success("Analysis Complete!")
                st.code(final_response.text, language="json")
                
            except Exception as e:
                st.error(f"An error occurred: {e}")