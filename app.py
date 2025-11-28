import streamlit as st
import easyocr
import cv2
import numpy as np
import sqlite3
import pandas as pd
from PIL import Image

# --- 1. 初始化設定 ---
# 設定頁面標題
st.set_page_config(page_title="車牌辨識與人員管理系統", layout="centered")

# 初始化 EasyOCR Reader (會下載模型，第一次執行會比較久)
# 'en' 包含英文與數字，足以應付台灣大部分車牌
@st.cache_resource
def load_reader():
    return easyocr.Reader(['en'])

reader = load_reader()

# --- 2. 資料庫功能 (SQLite) ---
DB_FILE = "lpr_system.db"

def init_db():
    """初始化資料庫"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS plates (
            plate_number TEXT PRIMARY KEY,
            owner_name TEXT,
            department TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_plate(plate, name, dept):
    """新增資料"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO plates (plate_number, owner_name, department) VALUES (?, ?, ?)", 
                  (plate.upper(), name, dept))
        conn.commit()
        st.success(f"成功新增車牌: {plate}")
    except sqlite3.IntegrityError:
        st.error("該車牌已存在！")
    finally:
        conn.close()

def delete_plate(plate):
    """刪除資料"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM plates WHERE plate_number = ?", (plate,))
    conn.commit()
    conn.close()
    st.warning(f"已刪除車牌: {plate}")

def get_owner(plate_text):
    """查詢車主"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT owner_name, department FROM plates WHERE plate_number = ?", (plate_text.upper(),))
    result = c.fetchone()
    conn.close()
    return result

def load_data():
    """讀取所有資料用於顯示"""
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM plates", conn)
    conn.close()
    return df

# 初始化 DB
init_db()

# --- 3. 圖像處理與辨識功能 ---
def recognize_plate(image_bytes):
    """接收圖片並回傳辨識到的文字"""
    # 將圖片轉為 OpenCV 格式
    file_bytes = np.asarray(bytearray(image_bytes.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    
    # 進行辨識
    results = reader.readtext(img)
    
    # 過濾結果，只取信心度較高且字數合理的
    detected_text = []
    for (bbox, text, prob) in results:
        # 簡單過濾：移除空格，轉大寫
        clean_text = text.replace(" ", "").replace("-", "").upper()
        if len(clean_text) >= 4 and prob > 0.3: # 假設車牌至少4碼
            detected_text.append(clean_text)
            
    return detected_text

# --- 4. 介面設計 (UI) ---

st.title("🚗 智慧車牌辨識系統")

# 側邊欄導航
menu = st.sidebar.selectbox("選單", ["📸 車牌辨識 (前台)", "⚙️ 後台管理"])

if menu == "⚙️ 後台管理":
    st.header("資料庫管理")
    
    # 新增車牌區塊
    with st.expander("➕ 新增車牌資料"):
        with st.form("add_form"):
            new_plate = st.text_input("車牌號碼 (例如: ABC-1234)")
            new_name = st.text_input("人員姓名")
            new_dept = st.text_input("部門/職稱")
            submit = st.form_submit_button("新增")
            if submit:
                if new_plate and new_name:
                    add_plate(new_plate.replace("-", "").replace(" ", ""), new_name, new_dept)
                else:
                    st.error("請填寫完整資訊")

    # 顯示與管理現有資料
    st.subheader("現有車牌列表")
    df = load_data()
    st.dataframe(df, use_container_width=True)
    
    # 刪除功能
    st.divider()
    del_plate = st.selectbox("選擇要刪除的車牌", df['plate_number'].unique() if not df.empty else [])
    if st.button("刪除選取車牌") and del_plate:
        delete_plate(del_plate)
        st.rerun()

elif menu == "📸 車牌辨識 (前台)":
    st.info("請使用手機直向拍攝，盡量讓車牌充滿畫面且清晰。")
    
    # 呼叫相機
    img_file = st.camera_input("點擊拍攝車牌")

    if img_file is not None:
        st.write("🔄 正在辨識中...")
        
        # 進行辨識
        candidates = recognize_plate(img_file)
        
        if not candidates:
            st.error("❌ 無法辨識出文字，請調整角度重拍。")
        else:
            found_match = False
            for text in candidates:
                owner = get_owner(text)
                if owner:
                    st.success(f"✅ 辨識成功！車牌: {text}")
                    st.metric(label="人員姓名", value=owner[0])
                    st.metric(label="部門/職稱", value=owner[1])
                    found_match = True
                    break
            
            if not found_match:
                st.warning(f"⚠️ 辨識出車牌: {candidates[0]}，但資料庫中無此資料。")
                st.write(f"所有可能的辨識結果: {candidates}")