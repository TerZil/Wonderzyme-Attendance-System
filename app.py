import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime, time
import io

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────

DB_FILE = "attendance.db"
PHOTO_DIR = "employee_photos"

os.makedirs(PHOTO_DIR, exist_ok=True)

# Default payroll rates (used if not set in DB)
DEFAULT_REGULAR_RATE = 150.0
DEFAULT_OT_MULTIPLIER = 1.25

# ────────────────────────────────────────────────
# DATABASE SETUP
# ────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Employees table
    c.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            position TEXT,
            department TEXT,
            added_date TEXT DEFAULT CURRENT_DATE,
            photo_path TEXT
        )
    ''')
    
    c.execute("PRAGMA table_info(employees)")
    columns = [col[1] for col in c.fetchall()]
    if 'photo_path' not in columns:
        c.execute("ALTER TABLE employees ADD COLUMN photo_path TEXT")
    
    # Attendance table
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            time_in TEXT,
            time_out TEXT,
            total_hours REAL,
            overtime_hours REAL DEFAULT 0,
            workload TEXT,
            remarks TEXT,
            inserted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (name) REFERENCES employees(name)
        )
    ''')
    
    c.execute("PRAGMA table_info(attendance)")
    columns = [col[1] for col in c.fetchall()]
    if 'overtime_hours' not in columns:
        c.execute("ALTER TABLE attendance ADD COLUMN overtime_hours REAL DEFAULT 0")
    
    # Settings table for payroll rates
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value REAL
        )
    ''')
    
    # Insert defaults if missing
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("regular_rate", DEFAULT_REGULAR_RATE))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("ot_multiplier", DEFAULT_OT_MULTIPLIER))
    
    conn.commit()
    conn.close()

def get_setting(key: str, default: float) -> float:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else default

def update_setting(key: str, value: float):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_all_employees() -> pd.DataFrame:
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("""
        SELECT 
            e.name, 
            e.position, 
            e.department, 
            e.added_date,
            e.photo_path,
            COUNT(a.id) as record_count
        FROM employees e
        LEFT JOIN attendance a ON e.name = a.name
        GROUP BY e.name
        ORDER BY e.name
    """, conn)
    conn.close()
    return df

def add_employee(name: str, position: str = "", department: str = "", photo_bytes=None, photo_ext=None) -> tuple[bool, str]:
    photo_path = None
    if photo_bytes and photo_ext:
        filename = f"{name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{photo_ext}"
        filepath = os.path.join(PHOTO_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(photo_bytes)
        photo_path = filename

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO employees (name, position, department, photo_path) VALUES (?, ?, ?, ?)",
            (name.strip(), position.strip(), department.strip(), photo_path)
        )
        conn.commit()
        return True, f"Profile uploaded successfully! {name} has been added."
    except sqlite3.IntegrityError:
        return False, "Employee name already exists."
    finally:
        conn.close()

def delete_employee(name: str) -> tuple[bool, str]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("SELECT photo_path FROM employees WHERE name = ?", (name,))
        photo = c.fetchone()
        if photo and photo[0]:
            photo_path = os.path.join(PHOTO_DIR, photo[0])
            if os.path.exists(photo_path):
                os.remove(photo_path)

        c.execute("DELETE FROM employees WHERE name = ?", (name,))
        conn.commit()
        return True, f"Employee '{name}' deleted."
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def delete_attendance_record(record_id: int) -> tuple[bool, str]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM attendance WHERE id = ?", (record_id,))
        conn.commit()
        return True, "Attendance record deleted successfully."
    except Exception as e:
        return False, f"Error deleting record: {str(e)}"
    finally:
        conn.close()

def update_attendance_record(record_id: int, time_in: str, time_out: str, workload: str, remarks: str) -> tuple[bool, str]:
    total_hours, _ = time_to_hours(time_in, time_out)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE attendance 
            SET time_in = ?, time_out = ?, total_hours = ?, workload = ?, remarks = ?
            WHERE id = ?
        """, (time_in, time_out, total_hours, workload, remarks, record_id))
        conn.commit()
        return True, "Attendance record updated successfully."
    except Exception as e:
        return False, f"Error updating record: {str(e)}"
    finally:
        conn.close()

def get_all_records() -> pd.DataFrame:
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM attendance ORDER BY date DESC, name", conn)
    conn.close()
    return df

def get_today_attendance(today_date: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(
        "SELECT id, name, time_in, time_out, total_hours, overtime_hours, workload, remarks "
        "FROM attendance WHERE date = ? ORDER BY name, time_in",
        conn,
        params=(today_date,)
    )
    conn.close()
    return df

def get_unique_employees():
    return get_all_employees()['name'].tolist()

init_db()

# ────────────────────────────────────────────────
# UI CONFIG & STYLE
# ────────────────────────────────────────────────

st.set_page_config(page_title="Wonderzyme Attendance", page_icon="🌱", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #f9fbf9; }
    .main-header {
        background-color: #2E7D32;
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 25px;
        border-bottom: 5px solid #FDD835;
    }
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e0e0e0;
    }
    .stButton>button {
        background-color: #2E7D32;
        color: white;
        border-radius: 5px;
        border: none;
    }
    .stButton>button:hover {
        background-color: #FDD835;
        color: #2E7D32;
        border: 1px solid #2E7D32;
    }
    [data-testid="stMetricValue"] { color: #2E7D32; }
    .today-date {
        font-size: 1.1rem;
        color: #2E7D32;
        font-weight: bold;
        margin: 0.5rem 0;
    }
    .employee-card {
        background: white;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        padding: 12px;
        margin-bottom: 12px;
    }
    .employee-photo {
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid #2E7D32;
    }
    </style>
    """, unsafe_allow_html=True)

# ────────────────────────────────────────────────
# HEADER & SIDEBAR
# ────────────────────────────────────────────────

today_str = datetime.now().strftime("%A, %B %d, %Y")
today_db_format = datetime.now().strftime("%Y-%m-%d")

st.markdown(f"""
    <div class="main-header">
        <h1>🌱 Wonderzyme</h1>
        <p style="margin:0;">Employee Attendance & Productivity Tracker</p>
        <div class="today-date">Today: {today_str}</div>
    </div>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.image("https://via.placeholder.com/150x50?text=Wonderzyme+Logo", use_container_width=True)
    st.markdown("---")
    page = st.selectbox("Menu", [
        "👤 Add Employee Profile",
        "👋 Clock In/Out",
        "📄 Records",
        "📊 Admin Dashboard",
        "⚙️ System Settings"
    ])
    st.markdown("---")
    st.caption("© 2026 Wonderzyme Solutions")

# ────────────────────────────────────────────────
# HELPER FUNCTIONS
# ────────────────────────────────────────────────

def time_to_hours(t_in: str, t_out: str) -> tuple[float | None, float]:
    if not (t_in and t_out):
        return None, 0.0
    
    try:
        fmt = "%H:%M"
        tin_dt = datetime.strptime(t_in, fmt)
        tout_dt = datetime.strptime(t_out, fmt)
        
        if tout_dt < tin_dt:
            tout_dt += pd.Timedelta(days=1)
        
        total_seconds = (tout_dt - tin_dt).total_seconds()
        total_hours = total_seconds / 3600
        
        # Overtime after 17:00
        overtime_start = datetime.strptime("17:00", fmt)
        overtime_start = overtime_start.replace(year=tin_dt.year, month=tin_dt.month, day=tin_dt.day)
        
        overtime_seconds = max(0, (tout_dt - overtime_start).total_seconds())
        overtime_hours = overtime_seconds / 3600
        
        # Lunch deduction (12:00-13:00)
        lunch_start, lunch_end = time(12, 0), time(13, 0)
        t_in_t, t_out_t = tin_dt.time(), tout_dt.time()
        overlap_start = max(t_in_t, lunch_start)
        overlap_end = min(t_out_t, lunch_end)
        
        if overlap_start < overlap_end:
            overlap_delta = datetime.combine(datetime.min, overlap_end) - datetime.combine(datetime.min, overlap_start)
            total_hours -= (overlap_delta.total_seconds() / 3600)
        
        return round(max(total_hours, 0), 2), round(overtime_hours, 2)
    except:
        return None, 0.0

# ────────────────────────────────────────────────
# PAGES
# ────────────────────────────────────────────────

if page == "👤 Add Employee Profile":
    st.subheader("Create New Employee Profile")
    st.markdown(f"<div class='today-date'>Today: {today_str}</div>", unsafe_allow_html=True)
    
    if 'profile_success' not in st.session_state:
        st.session_state.profile_success = None
    
    if st.session_state.profile_success:
        st.success(st.session_state.profile_success)
    
    with st.form("employee_form", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            name = st.text_input("Full Name *", placeholder="e.g. Juan Dela Cruz")
            position = st.text_input("Position", placeholder="e.g. Software Engineer")
            department = st.text_input("Department / Team", placeholder="e.g. Development")
        with col2:
            st.write("Photo")
            uploaded_photo = st.file_uploader("", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
        
        submitted = st.form_submit_button("Create Profile")
    
    if submitted:
        if not name.strip():
            st.error("Full Name is required.")
        else:
            photo_bytes = None
            photo_ext = None
            if uploaded_photo is not None:
                photo_bytes = uploaded_photo.getvalue()
                photo_ext = uploaded_photo.name.split('.')[-1].lower()
            
            success, message = add_employee(name, position, department, photo_bytes, photo_ext)
            if success:
                st.session_state.profile_success = f"Profile uploaded successfully! {name.strip()} has been added."
                st.success(st.session_state.profile_success)
                st.rerun()
            else:
                st.error(message)
                st.session_state.profile_success = None

elif page == "👋 Clock In/Out":
    st.subheader("Daily Time Record")
    st.markdown(f"<div class='today-date'>Today: {today_str}</div>", unsafe_allow_html=True)
    
    employees_df = get_all_employees()
    
    if employees_df.empty:
        st.warning("No employees found. Please add an employee profile first.")
    else:
        employees = employees_df['name'].tolist()
        
        with st.form("attendance_form", clear_on_submit=True):
            name = st.selectbox("Employee", employees)
            col1, col2 = st.columns([2, 1])
            with col1:
                workload = st.text_input("Tasks Completed Today")
            with col2:
                t_in = st.time_input("Clock In", value=time(8, 0))
                t_out = st.time_input("Clock Out", value=time(17, 0))
            
            remarks = st.text_area("Remarks / OT Notes")
            submitted = st.form_submit_button("Submit Attendance")

        if submitted:
            ti_s, to_s = t_in.strftime("%H:%M"), t_out.strftime("%H:%M")
            total_hrs, ot_hrs = time_to_hours(ti_s, to_s)
            today = datetime.now().strftime("%Y-%m-%d")
            
            conn = sqlite3.connect(DB_FILE)
            conn.execute(
                'INSERT INTO attendance (name, date, time_in, time_out, total_hours, overtime_hours, workload, remarks) VALUES (?,?,?,?,?,?,?,?)',
                (name, today, ti_s, to_s, total_hrs, ot_hrs, workload, remarks)
            )
            conn.commit()
            conn.close()
            
            # Success message with clock in/out details
            ot_text = f" + {ot_hrs:.1f} hrs OT" if ot_hrs > 0 else ""
            clock_msg = f"**Clocked in/out successfully!**\n\n**{name}**\n- In: {ti_s}\n- Out: {to_s}\n- Total: {total_hrs:.1f} hrs{ot_text}\n\nHave a great day!"
            st.success(clock_msg)
            st.rerun()

elif page == "📄 Records":
    st.subheader("Employee Profiles & Attendance History")
    st.markdown(f"<div class='today-date'>Today: {today_str}</div>", unsafe_allow_html=True)
    
    # Today's Attendance with labeled columns
    st.write("### Today's Attendance")
    today_df = get_today_attendance(today_db_format)
    
    if today_df.empty:
        st.info("No attendance records entered today yet.")
    else:
        today_df_display = today_df.copy()
        today_df_display['notes'] = (
            today_df_display['workload'].fillna('') + " | " + today_df_display['remarks'].fillna('')
        ).str.strip().replace('', '—')
        today_df_display['overtime_hours'] = today_df_display['overtime_hours'].fillna(0).round(1)
        today_df_display['total_hours'] = today_df_display['total_hours'].fillna(0).round(1)
        
        # Main table with labels
        st.dataframe(
            today_df_display[['name', 'time_in', 'time_out', 'total_hours', 'overtime_hours', 'notes']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("Name", width="medium"),
                "time_in": st.column_config.TextColumn("Start Time"),
                "time_out": st.column_config.TextColumn("End Time"),
                "total_hours": st.column_config.NumberColumn("Hours", format="%.1f"),
                "overtime_hours": st.column_config.NumberColumn("Overtime (hrs)", format="%.1f"),
                "notes": st.column_config.TextColumn("Notes", width="large")
            }
        )
        
        # Manage records (edit/delete)
        st.write("### Manage Today's Records")
        for idx, row in today_df.iterrows():
            col1, col2, col3 = st.columns([5, 1, 1])
            col1.markdown(f"**{row['name']}** — {row['time_in']} to {row['time_out']} ({row['total_hours']:.1f} hrs | {row['overtime_hours']:.1f} OT)")
            
            # Edit
            if col2.button("✏️ Edit", key=f"edit_{row['id']}"):
                with st.form(f"edit_form_{row['id']}"):
                    new_time_in = st.time_input("Start Time", value=datetime.strptime(row['time_in'], "%H:%M").time() if row['time_in'] else time(8,0))
                    new_time_out = st.time_input("End Time", value=datetime.strptime(row['time_out'], "%H:%M").time() if row['time_out'] else time(17,0))
                    new_workload = st.text_input("Workload / Tasks", value=row['workload'] or "")
                    new_remarks = st.text_area("Remarks", value=row['remarks'] or "")
                    save = st.form_submit_button("Save Changes")
                    
                    if save:
                        ti_s = new_time_in.strftime("%H:%M")
                        to_s = new_time_out.strftime("%H:%M")
                        success, msg = update_attendance_record(row['id'], ti_s, to_s, new_workload, new_remarks)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
            
            # Delete
            delete_key = f"del_att_{row['id']}"
            if col3.button("🗑️ Delete", key=delete_key):
                if st.session_state.get(f"confirm_att_{row['id']}", False):
                    success, msg = delete_attendance_record(row['id'])
                    if success:
                        st.success(msg)
                        st.session_state.pop(f"confirm_att_{row['id']}", None)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.session_state[f"confirm_att_{row['id']}"] = True
                    st.warning("Confirm delete this record? Click Delete again.")
        
        # Download button
        if not today_df.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                today_df_display.to_excel(writer, index=False, sheet_name="Today's Attendance")
            output.seek(0)
            
            st.download_button(
                label="Download Today's Attendance (Excel)",
                data=output,
                file_name=f"Wonderzyme_Today_Attendance_{today_db_format}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_today"
            )
        
        st.metric("People Clocked In Today", len(today_df))
    
    st.markdown("---")
    
    # Employee Profiles with Search Bar
    st.write("### Employee Profiles")
    employees_df = get_all_employees()
    
    if employees_df.empty:
        st.info("No employees added yet. Go to 'Add Employee Profile' to create one.")
    else:
        search_term = st.text_input("Search by name", placeholder="Type employee name...", key="profile_search")
        search_term = search_term.strip().lower()
        
        if search_term:
            filtered_df = employees_df[employees_df['name'].str.lower().str.contains(search_term)]
        else:
            filtered_df = employees_df.copy()
        
        if filtered_df.empty and search_term:
            st.warning(f"No employees found matching '{search_term}'")
        elif filtered_df.empty:
            st.info("No employees added yet.")
        else:
            for idx, row in filtered_df.iterrows():
                expander_label = f"{row['name']} • {row['position'] or '—'} • Records: {row['record_count']}"
                with st.expander(expander_label):
                    cols = st.columns([1, 5, 3])
                    
                    with cols[0]:
                        photo_path = row['photo_path']
                        full_photo_path = os.path.join(PHOTO_DIR, photo_path) if photo_path else None
                        
                        if full_photo_path and os.path.exists(full_photo_path):
                            st.image(full_photo_path, width=90, clamp=True)
                        else:
                            initials_url = f"https://ui-avatars.com/api/?name={row['name'].replace(' ', '+')}&background=2E7D32&color=fff&size=90&bold=true&rounded=true"
                            st.image(initials_url, width=90, clamp=True)
                    
                    with cols[1]:
                        st.markdown(f"**{row['name']}**")
                        st.caption(f"Added: {row['added_date']} • Position: {row['position'] or '—'} • Dept: {row['department'] or '—'}")
                        
                        emp_df = get_all_records()
                        emp_df = emp_df[emp_df["name"] == row['name']]
                        
                        if emp_df.empty:
                            st.info("No attendance records yet for this employee.")
                        else:
                            total_hrs = emp_df['total_hours'].sum() or 0
                            ot_hrs = emp_df['overtime_hours'].sum() or 0
                            days_worked = emp_df['date'].nunique()
                            avg_hrs = emp_df['total_hours'].mean() if days_worked > 0 else 0
                            
                            m1, m2, m3, m4 = st.columns(4)
                            m1.metric("Total Hours", f"{total_hrs:.1f}")
                            m2.metric("Overtime Hours", f"{ot_hrs:.1f}")
                            m3.metric("Days Worked", days_worked)
                            m4.metric("Avg Hours/Day", f"{avg_hrs:.1f}")
                            
                            # Payroll calculation (lifetime for this employee)
                            regular_rate = get_setting("regular_rate", 150.0)
                            ot_multiplier = get_setting("ot_multiplier", 1.25)
                            regular_pay = total_hrs * regular_rate
                            ot_pay = ot_hrs * regular_rate * ot_multiplier
                            total_pay = regular_pay + ot_pay
                            
                            p1, p2, p3 = st.columns(3)
                            p1.metric("Regular Pay", f"₱{regular_pay:,.2f}")
                            p2.metric("Overtime Pay", f"₱{ot_pay:,.2f}")
                            p3.metric("Total Pay", f"₱{total_pay:,.2f}")
                            
                            st.write("**Attendance History**")
                            st.dataframe(
                                emp_df.drop(columns=["id", "inserted_at", "name"]),
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "remarks": st.column_config.TextColumn("Remarks", width="medium"),
                                    "overtime_hours": st.column_config.NumberColumn("Overtime (hrs)", format="%.1f")
                                }
                            )
                    
                    with cols[2]:
                        delete_key = f"del_{row['name']}_{idx}"
                        if st.button("🗑️ Delete Profile", key=delete_key, type="secondary"):
                            if st.session_state.get(f"confirm_{row['name']}", False):
                                success, msg = delete_employee(row['name'])
                                if success:
                                    st.success(msg)
                                    st.session_state.pop(f"confirm_{row['name']}", None)
                                    st.rerun()
                                else:
                                    st.error(msg)
                            else:
                                st.session_state[f"confirm_{row['name']}"] = True
                                st.warning(f"Confirm delete **{row['name']}** and all their records? Click again.")

elif page == "📊 Admin Dashboard":
    st.subheader("Management Overview")
    st.markdown(f"<div class='today-date'>Today: {today_str}</div>", unsafe_allow_html=True)
    
    df = get_all_records()
    if not df.empty:
        summary = df.groupby("name").agg(
            Total_Hours=("total_hours", "sum"),
            Overtime_Hours=("overtime_hours", "sum"),
            Days=("date", "nunique"),
            Last_Active=("date", "max")
        ).reset_index()
        
        st.write("### Employee Summary")
        st.dataframe(summary, use_container_width=True, hide_index=True)
        
        st.write("### All Logs")
        st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)
    else:
        st.info("No attendance records yet.")

elif page == "⚙️ System Settings":
    st.subheader("System Settings")
    st.markdown(f"<div class='today-date'>Today: {today_str}</div>", unsafe_allow_html=True)
    
    regular_rate = get_setting("regular_rate", DEFAULT_REGULAR_RATE)
    ot_multiplier = get_setting("ot_multiplier", DEFAULT_OT_MULTIPLIER)
    
    st.write("### Payroll Rates")
    with st.form("rates_form"):
        new_regular = st.number_input("Regular Hourly Rate (₱)", value=regular_rate, min_value=0.0, step=1.0)
        new_ot_mult = st.number_input("Overtime Multiplier (e.g. 1.25 for 125%)", value=ot_multiplier, min_value=1.0, step=0.05)
        save_rates = st.form_submit_button("Save Rates")
        
        if save_rates:
            update_setting("regular_rate", new_regular)
            update_setting("ot_multiplier", new_ot_mult)
            st.success("Rates updated successfully!")
            st.rerun()
    
    st.info("These rates are used to calculate pay in employee profiles and dashboard.")