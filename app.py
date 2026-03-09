import os
import time
import json
import io
import datetime
import urllib.request
import xml.etree.ElementTree as ET
import base64
import concurrent.futures
from PIL import Image
import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import yfinance as yf

# ==========================================
# SECRET KEY INJECTION
# ==========================================
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

try:
    APP_PIN = st.secrets["MASTER_PASSWORD"]
except KeyError:
    st.error("System Error: MASTER_PASSWORD not found in secrets.")
    st.stop()

# ==========================================
# LIVE DATA FETCHERS
# ==========================================
def get_live_market_news():
    headlines = []
    feeds = [
        ('ForexLive', 'https://www.forexlive.com/feed/news'),
        ('Yahoo Finance', 'https://finance.yahoo.com/news/rssindex'),
        ('WSJ Markets', 'https://feeds.a.dj.com/rss/RSSMarketsMain.xml')
    ]
    for source, url in feeds:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            for item in root.findall('.//item')[:3]:
                title = item.find('title').text
                headlines.append(f"[{source}] {title}")
        except Exception: continue 
    return "\n".join(headlines) if headlines else "- News feeds temporarily unavailable."

def get_live_candles(ticker, timeframe_choice):
    if not ticker or "UNKNOWN" in ticker.upper(): return "No ticker provided."
    try:
        output_tables = []
        tf_mapping = {"1m": "1m", "5m": "5m", "15m": "15m", "1H": "1h", "4H": "4h", "1D": "1d"}
        for ui_label, yf_interval in tf_mapping.items():
            if ui_label in timeframe_choice:
                data = yf.download(ticker, period="1mo" if yf_interval in ["1d", "4h"] else "5d", interval=yf_interval)
                if not data.empty:
                    df = data[['Open', 'High', 'Low', 'Close']].tail(30)
                    df.index = df.index.strftime('%Y-%m-%d %H:%M')
                    output_tables.append(f"=== {ui_label} CANDLES ===\n" + df.round(4).to_string())
        return "\n\n".join(output_tables) if output_tables else "Data fetch failed."
    except Exception as e: return f"Statistical Data Error: {e}"

def get_image_base64(image_path):
    try:
        with open(image_path, "rb") as img_file: return base64.b64encode(img_file.read()).decode()
    except: return ""

logo_base64 = get_image_base64("fdm logo.png")
logo_html = f'<img src="data:image/png;base64,{logo_base64}" style="width: 140px; border-radius: 12px;">' if logo_base64 else '<h1>🧠</h1>'

def fetch_agent_response(model, role, index, prompt, images, temp):
    """Executes a single AI agent request asynchronously"""
    try:
        resp = model.generate_content([prompt] + images, generation_config={"temperature": temp})
        return role, index, resp.text
    except Exception as e:
        return role, index, f"WARNING: Agent timeout ({str(e)})"

# ==========================================
# SYSTEM INSTRUCTION
# ==========================================
SYSTEM_INSTRUCTION = """Senior Quantitative Analyst. Adhere strictly to IFX FDM Framework (Levels, Structure, Time, MTF Alignment). Unified MTF Consensus."""

# ==========================================
# UI SETUP & CSS
# ==========================================
st.set_page_config(page_title="IFX Master Brain", page_icon="🧠", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; color: #e2e8f0; }
    h1, h2, h3 { color: #ffffff !important; font-weight: 700 !important; }
    .neon-text { color: #00d26a; text-shadow: 0 0 10px rgba(0, 210, 106, 0.4); }
    .sub-text { color: #94a3b8; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;}
    .login-container { background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(0, 210, 106, 0.3); border-radius: 16px; padding: 40px; text-align: center; margin-top: 50px; }
    .glass-card { background: rgba(30, 41, 59, 0.5); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 24px; margin-bottom: 20px; }
    .bias-card-bullish { border-left: 4px solid #00d26a; background: linear-gradient(135deg, rgba(0, 210, 106, 0.1), transparent); }
    .bias-card-bearish { border-left: 4px solid #ff4b4b; background: linear-gradient(135deg, rgba(255, 75, 75, 0.1), transparent); }
    .bias-card-neutral { border-left: 4px solid #ffc107; }
    .bias-text-bullish { color: #00d26a; font-size: 32px; font-weight: 800; }
    .bias-text-bearish { color: #ff4b4b; font-size: 32px; font-weight: 800; }
    .bias-text-neutral { color: #ffc107; font-size: 32px; font-weight: 800; }
    .level-card { padding: 16px; border-radius: 8px; margin-bottom: 12px; background: #1e293b; border-left: 5px solid #3b82f6; }
    .level-bullish { border-left-color: #00d26a; }
    .level-bearish { border-left-color: #ff4b4b; }
    .level-inval { border-left-color: #f97316; }
    .level-price { font-size: 24px; font-weight: bold; font-family: monospace; color: #ffffff !important; }
    div.stButton > button:first-child { background-color: #00d26a !important; color: #000 !important; font-weight: bold; width: 100%; border-radius: 8px; height: 50px; transition: 0.3s; }
    div.stButton > button:first-child:hover { background-color: #00ff81 !important; transform: scale(1.02); }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# AUTH SYSTEM
# ==========================================
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f'<div class="login-container">{logo_html}<h1 class="neon-text">IFX MASTER BRAIN</h1><p class="sub-text">FDM Mult-Agent Engine</p></div>', unsafe_allow_html=True)
        pin_input = st.text_input("ENTER DECRYPTION KEY", type="password")
        if st.button("INITIALIZE ENGINE"):
            if pin_input == APP_PIN:
                st.session_state.authenticated = True
                st.rerun()
            else: st.error("Access Denied.")
    st.stop()

# ==========================================
# MAIN INTERFACE
# ==========================================
st.markdown(f'<div style="text-align: center; margin-top: 20px; margin-bottom: 30px;">{logo_html}<h2 class="neon-text">IFX MASTER BRAIN</h2><p class="sub-text">Hybrid Quant Consensus Dashboard</p></div>', unsafe_allow_html=True)

with st.container(border=True):
    col_input1, col_input2 = st.columns([1, 2])
    with col_input1:
        st.markdown("### 📊 Statistical Feed")
        ticker_input = st.text_input("Asset Ticker", placeholder="e.g. EURUSD=X")
        tf_options = ["1D", "4H", "1H", "15m", "5m", "1m", "4H + 1H", "1H + 15m"]
        tf_selection = st.selectbox("Statistical Timeframe", tf_options, index=7)
        exec_mode = st.radio("Execution Engine", ["⚡ Lightning (1 Agent per Council)", "🧠 Deep Consensus (3 Agents per Council)"], index=1)
    with col_input2:
        st.markdown("### 📝 Contextual Feed")
        trading_notes = st.text_area("Qualitative Input", placeholder="E.g. Watch the sweep of NY midnight open...", height=230)
    uploaded_files = st.file_uploader("Upload MTF Chart Array (Max 3)", accept_multiple_files=True)

if uploaded_files:
    cols = st.columns(len(uploaded_files[:3]))
    for i, file in enumerate(uploaded_files[:3]):
        cols[i].image(file, caption=f"Data Node {i+1}", use_container_width=True)

    if st.button("▶ EXECUTE FDM MATRIX"):
        with st.status("🧠 Initiating Hybrid Matrix...", expanded=True) as status:
            vertexai.init(project=PROJECT_ID, location=REGION)
            master_brain = GenerativeModel(model_name=TUNED_ENDPOINT_ID, system_instruction=SYSTEM_INSTRUCTION)
            
            # Vision Processing (NO CROP)
            image_parts = []
            for file in uploaded_files[:3]:
                img = Image.open(file).convert("RGB")
                # Resizing only for API limits, keeping full original image
                if img.width > 1600: img = img.resize((1600, int(img.height * (1600/img.width))), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=85)
                image_parts.append(Part.from_data(data=buf.getvalue(), mime_type="image/jpeg"))

            ticker_to_use = ticker_input.strip().upper()
            live_news = get_live_market_news()
            live_candles = get_live_candles(ticker_to_use, tf_selection)
            live_date = datetime.datetime.now().strftime("%A, %B %d, %Y")

            # Determine Agent Count
            num_agents = 3 if "Deep" in exec_mode else 1
            
            # Prompts
            tech_prompt = f"Analyze charts via FDM. Ticker: {ticker_to_use}. Date: {live_date}. Stats: {live_candles}. Notes: {trading_notes}"
            fundy_prompt = f"Fundamental Council Member. Asset: {ticker_to_use}. News: {live_news}. Context: {trading_notes}. Provide an institutional macro outlook."

            # 🚀 PARALLEL EXECUTION (Tech + Fundy Arrays)
            status.update(label=f"⚡ Firing Parallel Threads: Launching {num_agents} Technical & {num_agents} Fundamental Nodes...", state="running")
            
            tech_drafts = []
            raw_fundy_drafts = []
            
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=8) # Increased workers for 6 concurrent tasks
            futures = {}
            
            # Submit Technical Agents
            for i in range(num_agents):
                futures[executor.submit(fetch_agent_response, master_brain, "Tech", i+1, tech_prompt, image_parts, 0.4)] = ("Tech", i+1)
            
            # Submit Fundamental Agents
            for i in range(num_agents):
                futures[executor.submit(fetch_agent_response, master_brain, "Fundy", i+1, fundy_prompt, [], 0.4)] = ("Fundy", i+1)
            
            # ⏳ 30-Second Timeout Gate
            done, not_done = concurrent.futures.wait(futures.keys(), timeout=30.0)
            
            for f in done:
                role, idx, text = f.result()
                if role == "Tech": tech_drafts.append(f"Tech Analyst {idx}: {text}")
                elif role == "Fundy": raw_fundy_drafts.append(f"Fundy Analyst {idx}: {text}")
            
            if not_done: 
                st.toast("⚠️ API Latency: Slow nodes dropped.", icon="⏳")
            executor.shutdown(wait=False, cancel_futures=True)

            # 🏛️ FUNDAMENTAL ARBITRATOR (Synthesize the 3 Fundy drafts)
            status.update(label="⚖️ Fundamental Master Arbitrator synthesizing macro data...", state="running")
            combined_fundy_text = "\n".join(raw_fundy_drafts) if raw_fundy_drafts else "Fundamental data unavailable."
            fundy_arb_prompt = f"""You are the FDM Fundamental Master Arbitrator.
            Review the {len(raw_fundy_drafts)} drafts from your fundamental council below regarding {ticker_to_use}:
            {combined_fundy_text}
            
            Synthesize these drafts into a single, brutal, 3-4 sentence institutional-grade macro backdrop. Focus on catalysts, bias, and sentiment."""
            
            fundy_arb_resp = master_brain.generate_content([fundy_arb_prompt], generation_config={"temperature": 0.2})
            final_macro_context = fundy_arb_resp.text

            # 🧠 MASTER ARBITRATOR (Final Synthesis)
            status.update(label="⚖️ Ultimate Master Arbitrator formatting consensus matrix...", state="running")
            tech_agent_texts = "\n".join(tech_drafts)
            
            synthesis_prompt = f"""
            You are the Ultimate Master Arbitrator. Review the independent analysis from the Technical Council and the finalized summary from the Fundamental Arbitrator:
            
            --- TECHNICAL COUNCIL DRAFTS ---
            {tech_agent_texts}
            
            --- FINAL FUNDAMENTAL CONSENSUS ---
            {final_macro_context}
            
            Today's exact date is {live_date}. 
            
            Your job is to find the true, logical Future Pivot Zone. Anchor your levels precisely to the structural visual wicks OR the mathematical highs/lows provided in the raw data.
            
            You MUST output a valid JSON exactly matching this structure:
            {{
              "structural_reasoning": "Explain the final consensus achieved from the drafts regarding the MTF structure.",
              "trade_summary": {{
                "Current Live Price": "Exact current price from the right edge",
                "Daily Pivot Zone": "Consensus exact price range. CRITICAL RULE: The bottom of this zone MUST be your Invalidation level (if Bullish), or the top of this zone MUST be your Invalidation level (if Bearish).",
                "Market Structure": "Consensus next move",
                "Time Context": "Session timing context",
                "MTF Alignment": "How HTF and LTF align",
                "Bias": "Bullish, Bearish, or Neutral",
                "Fundamental Context": "Inject the exact Final Fundamental Consensus text here.",
                "Levels": [
                  {{"Level Type": "Target 1 (Partial)", "Price Point": "First macro target in the direction of the main bias", "Condition / Notes": "What to look for here"}},
                  {{"Level Type": "Target 2 (Final)", "Price Point": "Second extended macro target in the direction of the main bias (if available)", "Condition / Notes": "What to look for here"}},
                  {{"Level Type": "Invalidation Zone", "Price Point": "Exact structural line in the sand. MUST be the exact outer boundary of the Daily Pivot Zone.", "Condition / Notes": "If this breaks, the primary bias changes"}},
                  {{"Level Type": "Counter-Bias Target", "Price Point": "Macro target strictly BEYOND the Invalidation Zone (Where price goes AFTER invalidation breaks)", "Condition / Notes": "What to look for here"}}
                ]
              }}
            }}
            """
            final_resp = master_brain.generate_content([synthesis_prompt] + image_parts, generation_config={"temperature": 0.1})
            raw_text = final_resp.text
            
            try:
                # Bulletproof Stripping
                json_str = raw_text.replace("```json", "").replace("```", "").strip()
                data = json.loads(json_str)

                # Logging Dataset
                try:
                    with open("fdm_training_dataset.jsonl", "a") as f: f.write(json.dumps({"ts": str(datetime.datetime.now()), "data": data}) + "\n")
                except: pass

                summary = data["trade_summary"]
                bias = summary.get("Bias", "Neutral")
                bias_class = bias.lower() if bias.lower() in ["bullish", "bearish"] else "neutral"

                st.markdown(f'<div class="glass-card bias-card-{bias_class}" style="text-align: center; padding: 30px;"><h3 style="color: #cbd5e1 !important;">MASTER CONSENSUS</h3><div class="bias-text-{bias_class}">{bias.upper()}</div></div>', unsafe_allow_html=True)
                
                l_col, r_col = st.columns([1.2, 1])
                with l_col:
                    st.markdown(f"📡 **Live Price:** `{summary.get('Current Live Price')}`")
                    st.markdown(f"<div class='glass-card' style='border-left: 4px solid #3b82f6;'><span class='sub-text'>🎯 PIVOT ZONE</span><br><b>{summary.get('Daily Pivot Zone')}</b></div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='glass-card'><span class='sub-text'>🏗️ STRUCTURE</span><br>{summary.get('Market Structure')}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='glass-card'><span class='sub-text'>🌍 MACRO</span><br>{summary.get('Fundamental Context')}</div>", unsafe_allow_html=True)
                with r_col:
                    st.markdown("### 🎯 MACRO ZONES")
                    for lv in summary.get("Levels", []):
                        lv_type = lv.get("Level Type", "Level")
                        color = "level-bullish" if "bullish" in bias_class and "Target" in lv_type else ("level-bearish" if "bearish" in bias_class and "Target" in lv_type else ("level-inval" if "Invalid" in lv_type else "level-normal"))
                        st.markdown(f'<div class="level-card {color}"><div class="sub-text">{lv_type}</div><div class="level-price">{lv.get("Price Point")}</div><div style="font-size:12px; font-style:italic; color:#94a3b8;">{lv.get("Condition / Notes")}</div></div>', unsafe_allow_html=True)
            except: st.code(raw_text)
