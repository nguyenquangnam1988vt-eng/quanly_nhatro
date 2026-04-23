import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
import os
import uuid
import re
import mimetypes
from PIL import Image
import streamlit_js_eval as sje
import plotly.express as px
import plotly.graph_objects as go

# ------------------ CẤU HÌNH TRANG ------------------
st.set_page_config(
    page_title="QL Lưu trú Pro",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ------------------ CSS MOBILE + UI ĐẸP ------------------
st.markdown("""
    <style>
        @media (max-width: 768px) {
            .stButton button { width: 100%; font-size: 1.1rem; padding: 0.4rem; }
            .stTextInput, .stSelectbox, .stDateInput, .stTextArea, .stNumberInput { font-size: 0.9rem; }
            h1 { font-size: 1.8rem; }
            h2 { font-size: 1.4rem; }
            .css-1v3fvcr, .css-1adrfps { padding: 8px; margin-bottom: 8px; }
        }
        .metric-card {
            background-color: #f0f2f6;
            border-radius: 12px;
            padding: 15px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .st-emotion-cache-1v0mbdj { padding: 1rem; }
    </style>
""", unsafe_allow_html=True)

# ------------------ KHỞI TẠO DATABASE (có INDEX & LOG) ------------------
def init_db():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        # Users
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password TEXT)''')
        # Facilities
        c.execute('''CREATE TABLE IF NOT EXISTS facilities (
            id TEXT PRIMARY KEY, name TEXT, type TEXT, lat REAL, lon REAL,
            responsible_name TEXT, responsible_dob TEXT, responsible_id_number TEXT,
            responsible_permanent_address TEXT, responsible_phone TEXT,
            responsible_id_image_path TEXT, facility_image_path TEXT,
            total_rooms INTEGER, created_at TEXT)''')
        # Residents
        c.execute('''CREATE TABLE IF NOT EXISTS residents (
            id TEXT PRIMARY KEY, facility_id TEXT, fullname TEXT, dob TEXT,
            id_number TEXT, permanent_address TEXT, id_image_path TEXT,
            phone TEXT, room_number TEXT, start_date TEXT, end_date TEXT,
            note_type TEXT, created_at TEXT,
            FOREIGN KEY (facility_id) REFERENCES facilities(id))''')
        # Audit logs
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, action TEXT, target_type TEXT, target_id TEXT,
            timestamp TEXT, details TEXT)''')
        # Indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_res_facility ON residents(facility_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_res_id_number ON residents(id_number)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_res_end_date ON residents(end_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_fac_type ON facilities(type)")
        # User mặc định
        c.execute("SELECT * FROM users WHERE username='admin'")
        if not c.fetchone():
            c.execute("INSERT INTO users VALUES ('admin', '123')")
        conn.commit()

def log_action(username, action, target_type, target_id, details=""):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("INSERT INTO logs (username, action, target_type, target_id, timestamp, details) VALUES (?,?,?,?,?,?)",
                  (username, action, target_type, target_id, datetime.now().isoformat(), details))
        conn.commit()

# ------------------ HÀM XỬ LÝ AN TOÀN ------------------
def safe_parse_date(date_str):
    """Chuyển đổi date string an toàn, trả về date hoặc None"""
    if not date_str or pd.isna(date_str):
        return None
    try:
        if isinstance(date_str, date):
            return date_str
        if isinstance(date_str, str):
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        return None
    except:
        return None

def validate_cccd(cccd):
    return bool(re.fullmatch(r'\d{12}', str(cccd))) if cccd else False

def validate_phone(phone):
    return bool(re.fullmatch(r'(0|\+84)[0-9]{9,10}', str(phone))) if phone else False

def validate_upload(file, max_size_mb=5):
    if file is None:
        return True, ""
    if file.size > max_size_mb * 1024 * 1024:
        return False, f"Kích thước tối đa {max_size_mb}MB"
    mime = mimetypes.guess_type(file.name)[0]
    if mime not in ['image/jpeg', 'image/png', 'image/jpg']:
        return False, "Chỉ chấp nhận JPEG/PNG"
    return True, ""

def save_uploaded_file(uploaded_file, subfolder=""):
    if uploaded_file is None:
        return ""
    valid, msg = validate_upload(uploaded_file)
    if not valid:
        st.error(msg)
        return ""
    os.makedirs("uploads", exist_ok=True)
    os.makedirs(f"uploads/{subfolder}", exist_ok=True)
    ext = uploaded_file.name.split('.')[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = f"uploads/{subfolder}/{filename}" if subfolder else f"uploads/{filename}"
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def get_current_location():
    """Lấy GPS với fallback và thông báo lỗi"""
    try:
        location = sje.get_geolocation()
        if location is None:
            st.warning("Không thể truy cập GPS. Vui lòng cho phép quyền hoặc nhập tay.")
            return None, None
        if 'coords' in location:
            lat = location['coords']['latitude']
            lon = location['coords']['longitude']
            if lat and lon:
                return lat, lon
        st.warning("Không lấy được tọa độ. Vui lòng nhập tay.")
        return None, None
    except Exception as e:
        st.warning(f"Lỗi GPS: {str(e)}")
        return None, None

# ------------------ CRUD CƠ SỞ ------------------
def add_facility(data, images):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''INSERT INTO facilities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (data['id'], data['name'], data['type'], data['lat'], data['lon'],
                   data['responsible_name'], data['responsible_dob'], data['responsible_id_number'],
                   data['responsible_permanent_address'], data['responsible_phone'],
                   images['resp_id_img'], images['fac_img'], data['total_rooms'], data['created_at']))
        conn.commit()
    log_action(st.session_state['username'], "CREATE", "facility", data['id'], f"Tên: {data['name']}")

def update_facility(data, images):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''UPDATE facilities SET name=?, type=?, lat=?, lon=?,
                     responsible_name=?, responsible_dob=?, responsible_id_number=?,
                     responsible_permanent_address=?, responsible_phone=?,
                     responsible_id_image_path=?, facility_image_path=?, total_rooms=?
                     WHERE id=?''',
                  (data['name'], data['type'], data['lat'], data['lon'],
                   data['responsible_name'], data['responsible_dob'], data['responsible_id_number'],
                   data['responsible_permanent_address'], data['responsible_phone'],
                   images['resp_id_img'], images['fac_img'], data['total_rooms'], data['id']))
        conn.commit()
    log_action(st.session_state['username'], "UPDATE", "facility", data['id'], f"Tên: {data['name']}")

def delete_facility(facility_id):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        # Lấy tên cơ sở để log
        c.execute("SELECT name FROM facilities WHERE id=?", (facility_id,))
        fac_name = c.fetchone()[0]
        c.execute("DELETE FROM residents WHERE facility_id=?", (facility_id,))
        c.execute("DELETE FROM facilities WHERE id=?", (facility_id,))
        conn.commit()
    log_action(st.session_state['username'], "DELETE", "facility", facility_id, f"Tên: {fac_name}")

def add_resident(data, id_image_path):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''INSERT INTO residents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (data['id'], data['facility_id'], data['fullname'], data['dob'],
                   data['id_number'], data['permanent_address'], id_image_path,
                   data['phone'], data['room_number'], data['start_date'], data['end_date'],
                   data['note_type'], data['created_at']))
        conn.commit()
    log_action(st.session_state['username'], "CREATE", "resident", data['id'], f"Tên: {data['fullname']}")

def update_resident(data, id_image_path):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''UPDATE residents SET fullname=?, dob=?, id_number=?,
                     permanent_address=?, id_image_path=?, phone=?, room_number=?,
                     start_date=?, end_date=?, note_type=? WHERE id=?''',
                  (data['fullname'], data['dob'], data['id_number'],
                   data['permanent_address'], id_image_path, data['phone'],
                   data['room_number'], data['start_date'], data['end_date'],
                   data['note_type'], data['id']))
        conn.commit()
    log_action(st.session_state['username'], "UPDATE", "resident", data['id'], f"Tên: {data['fullname']}")

def delete_resident(resident_id):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("SELECT fullname FROM residents WHERE id=?", (resident_id,))
        res_name = c.fetchone()[0]
        c.execute("DELETE FROM residents WHERE id=?", (resident_id,))
        conn.commit()
    log_action(st.session_state['username'], "DELETE", "resident", resident_id, f"Tên: {res_name}")

def get_facilities(search_term=None, filter_type=None):
    query = "SELECT * FROM facilities"
    params = []
    conditions = []
    if search_term:
        conditions.append("name LIKE ?")
        params.append(f"%{search_term}%")
    if filter_type and filter_type != "Tất cả":
        conditions.append("type = ?")
        params.append(filter_type)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC"
    with sqlite3.connect('database.db') as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df

def get_residents(facility_id=None, search_term=None):
    query = "SELECT * FROM residents"
    params = []
    if facility_id:
        query += " WHERE facility_id = ?"
        params.append(facility_id)
        if search_term:
            query += " AND (fullname LIKE ? OR id_number LIKE ?)"
            params.extend([f"%{search_term}%", f"%{search_term}%"])
    elif search_term:
        query += " WHERE fullname LIKE ? OR id_number LIKE ?"
        params.extend([f"%{search_term}%", f"%{search_term}%"])
    query += " ORDER BY created_at DESC"
    with sqlite3.connect('database.db') as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df

# ------------------ GIAO DIỆN CHÍNH ------------------
def login():
    st.sidebar.title("🔐 Đăng nhập")
    username = st.sidebar.text_input("Tên đăng nhập")
    password = st.sidebar.text_input("Mật khẩu", type="password")
    if st.sidebar.button("Đăng nhập"):
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
            if c.fetchone():
                st.session_state['logged_in'] = True
                st.session_state['username'] = username
                st.success("Đăng nhập thành công!")
                st.rerun()
            else:
                st.error("Sai tên đăng nhập hoặc mật khẩu")

def main_app():
    st.title("🏨 Quản lý lưu trú Pro")
    # Sidebar đẹp
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/619/619015.png", width=80)
        st.write(f"👋 **{st.session_state['username']}**")
        if st.button("🚪 Đăng xuất", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        st.markdown("---")
        st.markdown("### 🔍 Tìm kiếm nhanh")
        search_fac = st.text_input("Tìm cơ sở (tên)")
        search_res = st.text_input("Tìm người (tên/CCCD)")
        filter_type = st.selectbox("Lọc loại cơ sở", ["Tất cả", "nhà trọ", "nhà dân", "nhà nghỉ", "khách sạn", "cơ sở tín ngưỡng", "công trường", "cơ sở khác"])
    
    tabs = st.tabs(["🏢 Cơ sở", "👥 Người lưu trú", "📊 Thống kê & Báo cáo", "📜 Nhật ký hệ thống"])
    
    # ------------------ TAB 1: CƠ SỞ ------------------
    with tabs[0]:
        st.subheader("📋 Danh sách cơ sở")
        facilities_df = get_facilities(search_term=search_fac, filter_type=filter_type)
        if facilities_df.empty:
            st.info("Không tìm thấy cơ sở nào.")
        else:
            for _, row in facilities_df.iterrows():
                with st.expander(f"🏠 {row['name']} - {row['type']}"):
                    col1, col2 = st.columns([1,2])
                    with col1:
                        if row['facility_image_path'] and os.path.exists(row['facility_image_path']):
                            st.image(row['facility_image_path'], width=150)
                        else:
                            st.image("https://placehold.co/150x100?text=No+Image", width=150)
                    with col2:
                        st.write(f"📍 GPS: {row['lat']:.5f}, {row['lon']:.5f}" if row['lat'] else "📍 Chưa có GPS")
                        st.write(f"👤 Chịu trách nhiệm: {row['responsible_name']} - {row['responsible_phone']}")
                        st.write(f"🚪 Tổng phòng: {row['total_rooms']}")
                        col_a, col_b, col_c = st.columns(3)
                        if col_a.button("✏️ Sửa", key=f"edit_fac_{row['id']}"):
                            st.session_state['edit_facility'] = row.to_dict()
                            st.rerun()
                        if col_b.button("🗑️ Xóa", key=f"del_fac_{row['id']}"):
                            delete_facility(row['id'])
                            st.success("Đã xóa cơ sở!")
                            st.rerun()
                        if col_c.button("👥 Xem người", key=f"view_res_{row['id']}"):
                            st.session_state['view_facility_id'] = row['id']
                            st.session_state['active_tab'] = 1
                            st.rerun()
        # Form thêm/sửa cơ sở
        st.markdown("---")
        if 'edit_facility' in st.session_state:
            st.subheader("✏️ Sửa cơ sở")
            fac = st.session_state['edit_facility']
        else:
            st.subheader("➕ Thêm cơ sở mới")
            fac = None
        with st.form("facility_form", clear_on_submit=not fac):
            name = st.text_input("Tên cơ sở *", value=fac['name'] if fac else "")
            type_opt = ["nhà trọ", "nhà dân", "nhà nghỉ", "khách sạn", "cơ sở tín ngưỡng", "công trường", "cơ sở khác"]
            type_ = st.selectbox("Loại hình", type_opt, index=type_opt.index(fac['type']) if fac and fac['type'] in type_opt else 0)
            col_gps1, col_gps2 = st.columns(2)
            with col_gps1:
                if st.button("📍 Lấy GPS", use_container_width=True):
                    lat, lon = get_current_location()
                    if lat and lon:
                        st.session_state['gps_lat'] = lat
                        st.session_state['gps_lon'] = lon
                        st.success(f"Đã lấy: {lat:.5f}, {lon:.5f}")
                    else:
                        st.error("Không lấy được GPS, vui lòng nhập tay")
                lat = st.number_input("Vĩ độ", value=st.session_state.get('gps_lat', fac['lat'] if fac and fac['lat'] else 0.0), format="%.6f")
                lon = st.number_input("Kinh độ", value=st.session_state.get('gps_lon', fac['lon'] if fac and fac['lon'] else 0.0), format="%.6f")
            st.markdown("**👤 Người chịu trách nhiệm**")
            resp_name = st.text_input("Họ tên *", value=fac['responsible_name'] if fac else "")
            resp_dob = st.date_input("Sinh ngày", value=datetime.strptime(fac['responsible_dob'], "%Y-%m-%d").date() if fac and fac['responsible_dob'] else date.today())
            resp_id_num = st.text_input("Số căn cước (12 số)", value=fac['responsible_id_number'] if fac else "")
            resp_perm_addr = st.text_area("Nơi đăng ký thường trú", value=fac['responsible_permanent_address'] if fac else "")
            resp_phone = st.text_input("Số điện thoại", value=fac['responsible_phone'] if fac else "")
            resp_id_img = st.file_uploader("Ảnh căn cước", type=["jpg","png","jpeg"], key="resp_id")
            fac_img = st.file_uploader("Ảnh cơ sở", type=["jpg","png","jpeg"], key="fac_img")
            total_rooms = st.number_input("Số phòng", min_value=0, value=int(fac['total_rooms']) if fac else 0, step=1)
            submitted = st.form_submit_button("✅ Lưu cơ sở")
            if submitted:
                # Validate
                if not name or not resp_name:
                    st.error("Tên cơ sở và người chịu trách nhiệm là bắt buộc.")
                elif resp_id_num and not validate_cccd(resp_id_num):
                    st.error("Số căn cước phải đúng 12 chữ số.")
                elif resp_phone and not validate_phone(resp_phone):
                    st.error("Số điện thoại không hợp lệ (Việt Nam).")
                else:
                    resp_img_path = save_uploaded_file(resp_id_img, "id_cards") if resp_id_img else (fac['responsible_id_image_path'] if fac else "")
                    fac_img_path = save_uploaded_file(fac_img, "facilities") if fac_img else (fac['facility_image_path'] if fac else "")
                    data = {
                        'id': fac['id'] if fac else str(uuid.uuid4()),
                        'name': name,
                        'type': type_,
                        'lat': lat,
                        'lon': lon,
                        'responsible_name': resp_name,
                        'responsible_dob': resp_dob.strftime("%Y-%m-%d"),
                        'responsible_id_number': resp_id_num,
                        'responsible_permanent_address': resp_perm_addr,
                        'responsible_phone': resp_phone,
                        'total_rooms': total_rooms,
                        'created_at': datetime.now().isoformat()
                    }
                    images = {'resp_id_img': resp_img_path, 'fac_img': fac_img_path}
                    if fac:
                        update_facility(data, images)
                        st.success("Cập nhật thành công!")
                        del st.session_state['edit_facility']
                    else:
                        add_facility(data, images)
                        st.success("Thêm mới thành công!")
                    st.rerun()
            if fac and st.form_submit_button("❌ Hủy sửa"):
                del st.session_state['edit_facility']
                st.rerun()
    
    # ------------------ TAB 2: NGƯỜI LƯU TRÚ ------------------
    with tabs[1]:
        st.subheader("👥 Quản lý người tạm trú/lưu trú")
        facilities_df = get_facilities()
        if facilities_df.empty:
            st.warning("Chưa có cơ sở nào. Hãy thêm cơ sở trước.")
        else:
            fac_options = {row['name']: row['id'] for _, row in facilities_df.iterrows()}
            selected_fac_name = st.selectbox("Chọn cơ sở", list(fac_options.keys()), key="fac_select")
            selected_fac_id = fac_options[selected_fac_name]
            # Tìm kiếm trong tab này
            search_local = st.text_input("🔍 Tìm người trong cơ sở này (tên/CCCD)", key="search_res_local")
            residents_df = get_residents(selected_fac_id, search_term=search_local if search_local else None)
            today = date.today()
            if not residents_df.empty:
                residents_df['end_date_dt'] = residents_df['end_date'].apply(lambda x: safe_parse_date(x))
                current = residents_df[residents_df['end_date_dt'] >= today] if not residents_df['end_date_dt'].isna().all() else pd.DataFrame()
                past = residents_df[residents_df['end_date_dt'] < today] if not residents_df['end_date_dt'].isna().all() else pd.DataFrame()
                st.markdown("### 🟢 Đang lưu trú/tạm trú")
                if current.empty:
                    st.info("Không có ai đang ở.")
                else:
                    for _, r in current.iterrows():
                        with st.expander(f"{r['fullname']} - Phòng {r['room_number']} (hết: {r['end_date']})"):
                            col1, col2 = st.columns([1,2])
                            with col1:
                                if r['id_image_path'] and os.path.exists(r['id_image_path']):
                                    st.image(r['id_image_path'], width=120)
                            with col2:
                                st.write(f"**Sinh:** {r['dob']}")
                                st.write(f"**CCCD:** {r['id_number']}")
                                st.write(f"**ĐKTT:** {r['permanent_address']}")
                                st.write(f"**SĐT:** {r['phone']}")
                                st.write(f"**Loại:** {r['note_type']}")
                            col_a, col_b = st.columns(2)
                            if col_a.button("✏️ Sửa", key=f"edit_res_{r['id']}"):
                                st.session_state['edit_resident'] = r.to_dict()
                                st.session_state['edit_facility_id'] = selected_fac_id
                                st.rerun()
                            if col_b.button("🗑️ Xóa", key=f"del_res_{r['id']}"):
                                delete_resident(r['id'])
                                st.success("Đã xóa!")
                                st.rerun()
                st.markdown("### 🔴 Đã từng lưu trú")
                if past.empty:
                    st.info("Chưa có người đã hết hạn.")
                else:
                    for _, r in past.iterrows():
                        with st.expander(f"{r['fullname']} - Đã rời ngày {r['end_date']}"):
                            st.write(f"**Phòng:** {r['room_number']}, **Loại:** {r['note_type']}")
                            st.write(f"**SĐT:** {r['phone']}")
            else:
                st.info("Không có người nào trong cơ sở này.")
            # Form thêm/sửa
            st.markdown("---")
            if 'edit_resident' in st.session_state:
                st.subheader("✏️ Sửa thông tin người")
                res = st.session_state['edit_resident']
            else:
                st.subheader("➕ Thêm người mới")
                res = None
            with st.form("resident_form", clear_on_submit=not res):
                fullname = st.text_input("Họ tên *", value=res['fullname'] if res else "")
                dob = st.date_input("Sinh ngày", value=safe_parse_date(res['dob']) if res and res['dob'] else date.today())
                id_number = st.text_input("Số căn cước (12 số)", value=res['id_number'] if res else "")
                perm_addr = st.text_area("Nơi đăng ký thường trú", value=res['permanent_address'] if res else "")
                id_img = st.file_uploader("Ảnh căn cước", type=["jpg","png","jpeg"], key="resident_id")
                phone = st.text_input("Số điện thoại", value=res['phone'] if res else "")
                room = st.text_input("Số phòng *", value=res['room_number'] if res else "")
                start_date = st.date_input("Ngày bắt đầu", value=safe_parse_date(res['start_date']) if res and res['start_date'] else date.today())
                end_date = st.date_input("Ngày kết thúc", value=safe_parse_date(res['end_date']) if res and res['end_date'] else date.today())
                note_type = st.radio("Loại hình", ["Tạm trú", "Lưu trú"], index=0 if not res else (0 if res['note_type']=="Tạm trú" else 1))
                submitted = st.form_submit_button("✅ Lưu người")
                if submitted:
                    if not fullname or not room:
                        st.error("Họ tên và số phòng là bắt buộc.")
                    elif id_number and not validate_cccd(id_number):
                        st.error("Căn cước phải 12 chữ số.")
                    elif phone and not validate_phone(phone):
                        st.error("Số điện thoại không hợp lệ.")
                    elif end_date <= start_date:
                        st.error("Ngày kết thúc phải sau ngày bắt đầu.")
                    else:
                        img_path = save_uploaded_file(id_img, "id_cards") if id_img else (res['id_image_path'] if res else "")
                        data_res = {
                            'id': res['id'] if res else str(uuid.uuid4()),
                            'facility_id': selected_fac_id,
                            'fullname': fullname,
                            'dob': dob.strftime("%Y-%m-%d"),
                            'id_number': id_number,
                            'permanent_address': perm_addr,
                            'phone': phone,
                            'room_number': room,
                            'start_date': start_date.strftime("%Y-%m-%d"),
                            'end_date': end_date.strftime("%Y-%m-%d"),
                            'note_type': note_type,
                            'created_at': datetime.now().isoformat()
                        }
                        if res:
                            update_resident(data_res, img_path)
                            st.success("Cập nhật thành công!")
                            del st.session_state['edit_resident']
                        else:
                            add_resident(data_res, img_path)
                            st.success("Thêm mới thành công!")
                        st.rerun()
                if res and st.form_submit_button("❌ Hủy sửa"):
                    del st.session_state['edit_resident']
                    st.rerun()
    
    # ------------------ TAB 3: THỐNG KÊ & BÁO CÁO ------------------
    with tabs[2]:
        st.subheader("📊 Thống kê tổng quan")
        # Metrics
        all_res = get_residents()
        all_fac = get_facilities()
        today = date.today()
        if not all_res.empty:
            all_res['end_date_dt'] = all_res['end_date'].apply(safe_parse_date)
            current_count = len(all_res[all_res['end_date_dt'] >= today])
            expired_count = len(all_res[all_res['end_date_dt'] < today])
            soon_count = len(all_res[(all_res['end_date_dt'] >= today) & (all_res['end_date_dt'] <= today + timedelta(days=7))])
        else:
            current_count = expired_count = soon_count = 0
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🏢 Tổng cơ sở", len(all_fac))
        col2.metric("👥 Đang lưu trú", current_count)
        col3.metric("⏰ Sắp hết hạn (<7 ngày)", soon_count, delta="cần theo dõi")
        col4.metric("📜 Đã rời đi", expired_count)
        # Biểu đồ theo loại hình cơ sở
        if not all_fac.empty:
            fig_type = px.bar(all_fac, x='type', title="Số lượng cơ sở theo loại hình", color='type', text_auto=True)
            st.plotly_chart(fig_type, use_container_width=True)
        # Biểu đồ tròn: tạm trú vs lưu trú
        if not all_res.empty:
            fig_pie = px.pie(all_res, names='note_type', title="Tỷ lệ Tạm trú / Lưu trú", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        # Biểu đồ cột: số người theo cơ sở (top 10)
        if not all_res.empty and not all_fac.empty:
            res_fac = all_res.merge(all_fac[['id','name']], left_on='facility_id', right_on='id', how='left')
            top_fac = res_fac['name'].value_counts().head(10).reset_index()
            top_fac.columns = ['Cơ sở', 'Số người']
            fig_top = px.bar(top_fac, x='Cơ sở', y='Số người', title="Top 10 cơ sở đông người nhất")
            st.plotly_chart(fig_top, use_container_width=True)
        # Danh sách sắp hết hạn
        st.subheader("⚠️ Danh sách người sắp hết hạn (dưới 7 ngày)")
        if not all_res.empty:
            soon_list = all_res[(all_res['end_date_dt'] >= today) & (all_res['end_date_dt'] <= today + timedelta(days=7))]
            if soon_list.empty:
                st.info("Không có ai sắp hết hạn.")
            else:
                for _, r in soon_list.iterrows():
                    fac_name = all_fac[all_fac['id']==r['facility_id']]['name'].values[0] if not all_fac.empty else "Không rõ"
                    st.write(f"- **{r['fullname']}** - {r['phone']} - {fac_name} - Hết hạn: {r['end_date']}")
    
    # ------------------ TAB 4: NHẬT KÝ ------------------
    with tabs[3]:
        st.subheader("📜 Nhật ký hoạt động")
        with sqlite3.connect('database.db') as conn:
            logs_df = pd.read_sql_query("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 200", conn)
        if logs_df.empty:
            st.info("Chưa có hoạt động nào.")
        else:
            st.dataframe(logs_df, use_container_width=True, height=500)
    
    # Xử lý chuyển tab từ nút "Xem người"
    if 'active_tab' in st.session_state:
        st.session_state.pop('active_tab')
        # không cần làm gì thêm, tab đã được set

# ------------------ LOGIN ------------------
def main():
    init_db()
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if not st.session_state['logged_in']:
        st.image("https://cdn-icons-png.flaticon.com/512/619/619015.png", width=120)
        st.title("Hệ thống quản lý lưu trú")
        login()
    else:
        main_app()

if __name__ == "__main__":
    main()