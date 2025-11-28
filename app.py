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

def clean_plate_text(text):
    """統一將車牌轉大寫並移除符號，方便比對"""
    return text.replace("-", "").replace(" ", "").upper()

def add_plate(plate, name, dept):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    plate_clean = clean_plate_text(plate)
    try:
        c.execute("INSERT INTO plates (plate_number, owner_name, department) VALUES (?, ?, ?)", 
                  (plate_clean, name, dept))
        conn.commit()
        return True, f"成功新增: {plate_clean}"
    except sqlite3.IntegrityError:
        return False, f"車牌已存在: {plate_clean}"
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
    plate_clean = clean_plate_text(plate_text)
    c.execute("SELECT owner_name, department FROM plates WHERE plate_number = ?", (plate_clean,))
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
        # 過濾邏輯：長度大於3且信心度大於0.3
        cleaned = clean_plate_text(text)
        if len(cleaned) >= 3 and prob > 0.3:
            detected_text.append(cleaned)
            
    return detected_text

# --- 4. 介面設計 (UI) ---

st.title("🚗 智慧車牌辨識系統")
menu = st.sidebar.selectbox("選單", ["📸 車牌辨識 (前台)", "⚙️ 後台管理"])

# ================= ⚙️ 後台管理區塊 =================
if menu == "⚙️ 後台管理":
    st.header("資料庫管理")
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
        st.markdown("支援 UTF-8 與 Excel (Big5) 格式 CSV。")
        uploaded_file = st.file_uploader("選擇 CSV 檔案", type=['csv'])
        
        if uploaded_file is not None:
            try:
                # 嘗試讀取 (自動偵測編碼)
                try:
                    df_upload = pd.read_csv(uploaded_file)
                except UnicodeDecodeError:
                    uploaded_file.seek(0)
                    df_upload = pd.read_csv(uploaded_file, encoding='big5')

                # 檢查欄位
                required_cols = {'車牌', '姓名', '部門'}
                if not required_cols.issubset(df_upload.columns):
                    st.error(f"欄位名稱錯誤！請確認 CSV 包含: {required_cols}")
                else:
                    st.write(f"預覽前 3 筆資料:")
                    st.dataframe(df_upload.head(3))
                    
                    if st.button("確認匯入資料庫"):
                        success_count = 0
                        fail_count = 0
                        progress_bar = st.progress(0)
                        
                        for index, row in df_upload.iterrows():
                            s, m = add_plate(str(row['車牌']), str(row['姓名']), str(row['部門']))
                            if s: success_count += 1
                            else: fail_count += 1
                            progress_bar.progress((index + 1) / len(df_upload))
                            
                        st.success(f"匯入完成！成功: {success_count}，重複/失敗: {fail_count}")

            except Exception as e:
                st.error(f"讀取失敗: {e}")

    with tab3:
        st.subheader("現有資料")
        df = load_data()
        st.dataframe(df, use_container_width=True)
        
        st.divider()
        del_plate = st.selectbox("選擇要刪除的車牌", df['plate_number'].unique() if not df.empty else [])
        if st.button("刪除") and del_plate:
            delete_plate(del_plate)
            st.rerun()

# ================= 📸 前台辨識區塊 (更新！) =================
elif menu == "📸 車牌辨識 (前台)":
    
    # 1. 拍照辨識
    st.subheader("📷 拍照辨識")
    img_file = st.camera_input("點擊拍攝")

    if img_file is not None:
        st.write("🔄 影像處理中...")
        candidates = recognize_plate(img_file)
        
        if not candidates:
            st.error("❌ 畫面中未偵測到文字")
        else:
            found = False
            for text in candidates:
                owner = get_owner(text)
                if owner:
                    st.success(f"✅ 辨識成功！車牌: {text}")
                    st.info(f"👤 姓名: {owner[0]}")
                    st.info(f"🏢 部門: {owner[1]}")
                    found = True
                    break
            if not found:
                st.warning(f"⚠️ 辨識出: {candidates}，但資料庫無此車牌。")

    st.divider() # 分隔線

    # 2. 手動查詢 (新增功能)
    st.subheader("🔍 手動輸入查詢")
    
    with st.form("manual_lookup"):
        # 使用 column 讓按鈕排在輸入框旁邊
        col1, col2 = st.columns([3, 1])
        with col1:
            manual_input = st.text_input("輸入車牌號碼", placeholder="例如: ABC-1234")
        with col2:
            st.write("") # 排版用空格
            st.write("")
            manual_submit = st.form_submit_button("查詢")

    if manual_submit:
        if manual_input:
            owner = get_owner(manual_input)
            if owner:
                st.success(f"✅ 查詢成功！車牌: {manual_input.upper()}")
                st.info(f"👤 姓名: {owner[0]}")
                st.info(f"🏢 部門: {owner[1]}")
            else:
                st.error(f"❌ 查無此車牌資料: {manual_input}")
        else:
            st.warning("請輸入車牌號碼")