import streamlit as st
import easyocr
import cv2
import numpy as np
import sqlite3
import pandas as pd

# --- 1. 初始化設定 ---
st.set_page_config(page_title="車牌辨識與人員管理系統", layout="centered")

@st.cache_resource
def load_reader():
    return easyocr.Reader(['en'])

reader = load_reader()

# --- 2. 資料庫功能 (SQLite) ---
DB_FILE = "lpr_system.db"

def init_db():
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
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 移除車牌中的特殊符號
    clean_plate = plate.replace("-", "").replace(" ", "").upper()
    try:
        c.execute("INSERT INTO plates (plate_number, owner_name, department) VALUES (?, ?, ?)", 
                  (clean_plate, name, dept))
        conn.commit()
        return True, f"成功新增: {clean_plate}"
    except sqlite3.IntegrityError:
        return False, f"車牌已存在: {clean_plate}"
    finally:
        conn.close()

def delete_plate(plate):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM plates WHERE plate_number = ?", (plate,))
    conn.commit()
    conn.close()

def get_owner(plate_text):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 查詢時也先移除符號
    clean_text = plate_text.replace("-", "").replace(" ", "").upper()
    c.execute("SELECT owner_name, department FROM plates WHERE plate_number = ?", (clean_text,))
    result = c.fetchone()
    conn.close()
    return result

def load_data():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM plates", conn)
    conn.close()
    return df

# 初始化 DB
init_db()

# --- 3. 圖像處理與辨識功能 ---
def recognize_plate(image_bytes):
    file_bytes = np.asarray(bytearray(image_bytes.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    results = reader.readtext(img)
    
    detected_text = []
    for (bbox, text, prob) in results:
        clean_text = text.replace(" ", "").replace("-", "").upper()
        # 簡單過濾：長度大於3且信心度大於0.3
        if len(clean_text) >= 3 and prob > 0.3:
            detected_text.append(clean_text)
            
    return detected_text

# --- 4. 介面設計 (UI) ---

st.title("🚗 智慧車牌辨識系統")
menu = st.sidebar.selectbox("選單", ["📸 車牌辨識 (前台)", "⚙️ 後台管理"])

if menu == "⚙️ 後台管理":
    st.header("資料庫管理")
    
    # === 分頁籤設計 (新增: 批次匯入功能) ===
    tab1, tab2, tab3 = st.tabs(["➕ 單筆新增", "📂 CSV 批次匯入", "📃 資料列表"])

    with tab1:
        st.subheader("單筆新增車牌")
        with st.form("add_form"):
            new_plate = st.text_input("車牌號碼")
            new_name = st.text_input("人員姓名")
            new_dept = st.text_input("部門/職稱")
            submit = st.form_submit_button("新增")
            if submit:
                if new_plate and new_name:
                    success, msg = add_plate(new_plate, new_name, new_dept)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.error("請填寫完整資訊")

    with tab2:
        st.subheader("批次匯入資料")
        st.markdown("請上傳 CSV 檔案，需包含欄位：`車牌`, `姓名`, `部門`")
        uploaded_file = st.file_uploader("選擇 CSV 檔案", type=['csv'])
        
        if uploaded_file is not None:
            try:
                # 讀取 CSV
                df_upload = pd.read_csv(uploaded_file)
                
                # 檢查欄位是否正確
                required_cols = {'車牌', '姓名', '部門'}
                if not required_cols.issubset(df_upload.columns):
                    st.error(f"CSV 格式錯誤！請確認包含以下欄位: {required_cols}")
                else:
                    st.write("預覽上傳資料 (前 5 筆):")
                    st.dataframe(df_upload.head())
                    
                    if st.button("確認匯入資料庫"):
                        success_count = 0
                        fail_count = 0
                        progress_bar = st.progress(0)
                        
                        for index, row in df_upload.iterrows():
                            # 呼叫新增函式
                            s, m = add_plate(str(row['車牌']), str(row['姓名']), str(row['部門']))
                            if s:
                                success_count += 1
                            else:
                                fail_count += 1
                            progress_bar.progress((index + 1) / len(df_upload))
                            
                        st.success(f"匯入完成！成功: {success_count} 筆，重複/失敗: {fail_count} 筆")
                        st.balloons() # 放個氣球慶祝一下
            except Exception as e:
                st.error(f"讀取檔案失敗: {e}")

    with tab3:
        st.subheader("現有車牌列表")
        df = load_data()
        st.dataframe(df, use_container_width=True)
        
        st.divider()
        st.write("刪除資料")
        del_plate = st.selectbox("選擇要刪除的車牌", df['plate_number'].unique() if not df.empty else [])
        if st.button("刪除選取車牌") and del_plate:
            delete_plate(del_plate)
            st.rerun()

elif menu == "📸 車牌辨識 (前台)":
    st.info("請使用手機直向拍攝，盡量讓車牌充滿畫面且清晰。")
    img_file = st.camera_input("點擊拍攝車牌")

    if img_file is not None:
        st.write("🔄 正在辨識中...")
        candidates = recognize_plate(img_file)
        
        if not candidates:
            st.error("❌ 無法辨識出文字")
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
                st.warning(f"⚠️ 辨識出車牌: {candidates[0]}，但無此資料。")
                st.write(f"所有辨識結果: {candidates}")