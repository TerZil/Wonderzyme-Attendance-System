import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime, time, date
import io

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────

DB_FILE = "attendance.db"
PHOTO_DIR = "employee_photos"

os.makedirs(PHOTO_DIR, exist_ok=True)

DEFAULT_REGULAR_RATE = 150.0
DEFAULT_OT_MULTIPLIER = 1.25

# ────────────────────────────────────────────────
# DATABASE FUNCTIONS
# ────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
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
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value REAL
        )
    ''')
    
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
        SELECT e.name, e.position, e.department, e.added_date, e.photo_path,
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

        c.execute("DELETE FROM attendance WHERE name = ?", (name,))
        c.execute("DELETE FROM employees WHERE name = ?", (name,))
        conn.commit()
        return True, f"Employee '{name}' and all records deleted."
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def clear_employee_attendance(name: str) -> tuple[bool, str]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM attendance WHERE name = ?", (name,))
        conn.commit()
        return True, f"All attendance records for {name} cleared."
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
        return True, "Attendance record deleted."
    except Exception as e:
        return False, f"Error deleting record: {str(e)}"
    finally:
        conn.close()

def update_attendance_record(record_id: int, time_in: str, time_out: str, workload: str, remarks: str) -> tuple[bool, str]:
    total_hours, overtime_hours = time_to_hours(time_in, time_out)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE attendance 
            SET time_in = ?, time_out = ?, total_hours = ?, overtime_hours = ?, workload = ?, remarks = ?
            WHERE id = ?
        """, (time_in, time_out, total_hours, overtime_hours, workload, remarks, record_id))
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
        
        overtime_start = datetime.strptime("17:00", fmt)
        overtime_start = overtime_start.replace(year=tin_dt.year, month=tin_dt.month, day=tin_dt.day)
        
        overtime_seconds = max(0, (tout_dt - overtime_start).total_seconds())
        overtime_hours = overtime_seconds / 3600
        
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
    .employee-photo {
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid #2E7D32;
    }
    .action-btn {
        padding: 4px 10px;
        font-size: 0.9rem;
    }
    .clear-btn {
        background-color: #d32f2f !important;
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)

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
        "⚙️ Payroll Rates"
    ])
    st.markdown("---")
    st.caption("© 2026 Wonderzyme Solutions")

# ────────────────────────────────────────────────
# SESSION STATE FOR EXPANDER PERSISTENCE
# ────────────────────────────────────────────────

if 'open_expanders' not in st.session_state:
    st.session_state.open_expanders = set()

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
            
            selected_date = st.date_input("Attendance Date", value=date.today(), max_value=date.today())
            selected_date_str = selected_date.strftime("%Y-%m-%d")
            
            col1, col2 = st.columns([2, 1])
            with col1:
                workload = st.text_input("Tasks Completed / Workload")
            with col2:
                t_in = st.time_input("Clock In", value=time(8, 0))
                t_out = st.time_input("Clock Out", value=time(17, 0))
            
            remarks = st.text_area("Remarks / OT Notes")
            submitted = st.form_submit_button("Submit Attendance", use_container_width=True)

        if submitted:
            ti_s, to_s = t_in.strftime("%H:%M"), t_out.strftime("%H:%M")
            total_hrs, ot_hrs = time_to_hours(ti_s, to_s)
            
            if total_hrs is None:
                st.error("Invalid time duration. Please check your Clock In/Out times.")
            else:
                conn = sqlite3.connect(DB_FILE)
                conn.execute(
                    'INSERT INTO attendance (name, date, time_in, time_out, total_hours, overtime_hours, workload, remarks) VALUES (?,?,?,?,?,?,?,?)',
                    (name, selected_date_str, ti_s, to_s, total_hrs, ot_hrs, workload, remarks)
                )
                conn.commit()
                conn.close()
                
                date_display = selected_date.strftime("%A, %B %d, %Y")
                task_text = workload.strip() if workload and workload.strip() else "No tasks specified"
                ot_line = f"- **Overtime:** {ot_hrs:.1f} hrs" if ot_hrs > 0 else ""
                
                st.markdown("---")
                st.success(f"**Attendance Recorded Successfully for {name}!**")
                st.markdown(f"""
**Summary for {date_display}:**

- **Time:** {ti_s} - {to_s}
- **Total Hours:** {total_hrs:.1f} hrs
{ot_line}
- **Task:** {task_text}
                """.strip())
                
                if remarks and remarks.strip():
                    st.markdown(f"""
**Remarks / Notes:**
{remarks}
                    """)
                
                st.markdown("---")
                st.info("Record saved successfully. You can now record another attendance or go to another page.")

elif page == "📄 Records":
    st.subheader("Employee Profiles & Attendance History")
    st.markdown(f"<div class='today-date'>Today: {today_str}</div>", unsafe_allow_html=True)
    
    # Today's Attendance
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
    
    # Employee Profiles
    st.write("### Employee Profiles")
    employees_df = get_all_employees()
    
    if employees_df.empty:
        st.info("No employees added yet.")
    else:
        search_term = st.text_input("Search by name", placeholder="Type employee name...", key="profile_search")
        search_term = search_term.strip().lower()
        
        filtered_df = employees_df[employees_df['name'].str.lower().str.contains(search_term)] if search_term else employees_df
        
        for _, row in filtered_df.iterrows():
            expander_key = f"exp_{row['name']}"
            
            # Restore expander state
            expanded = expander_key in st.session_state.open_expanders
            
            with st.expander(f"{row['name']} • {row['position'] or '—'} • Records: {row['record_count']}", expanded=expanded):
                # Mark as open
                if expander_key not in st.session_state.open_expanders:
                    st.session_state.open_expanders.add(expander_key)
                
                cols = st.columns([1.2, 5, 1])
                
                with cols[0]:
                    photo_path = row['photo_path']
                    full_photo_path = os.path.join(PHOTO_DIR, photo_path) if photo_path else None
                    
                    if full_photo_path and os.path.exists(full_photo_path):
                        st.image(full_photo_path, width=90)
                    else:
                        initials = ''.join(word[0].upper() for word in row['name'].split()[:2])
                        st.markdown(f"""
                        <div style="background-color:#2E7D32; color:white; width:90px; height:90px; border-radius:50%; 
                        display:flex; align-items:center; justify-content:center; font-size:36px; font-weight:bold;">
                            {initials}
                        </div>
                        """, unsafe_allow_html=True)
                
                with cols[1]:
                    st.markdown(f"**{row['name']}**")
                    st.caption(f"Added: {row['added_date']} • Position: {row['position'] or '—'} • Dept: {row['department'] or '—'}")
                    
                    emp_df = get_all_records()
                    emp_df = emp_df[emp_df["name"] == row['name']].copy()
                    
                    if not emp_df.empty:
                        total_hrs = emp_df['total_hours'].sum() or 0
                        ot_hrs = emp_df['overtime_hours'].sum() or 0
                        days_worked = emp_df['date'].nunique()
                        avg_hrs = emp_df['total_hours'].mean() if days_worked > 0 else 0
                        
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Total Hours", f"{total_hrs:.1f}")
                        m2.metric("Overtime Hours", f"{ot_hrs:.1f}")
                        m3.metric("Days Worked", days_worked)
                        m4.metric("Avg Hours/Day", f"{avg_hrs:.1f}")
                        
                        regular_rate = get_setting("regular_rate", 150.0)
                        ot_multiplier = get_setting("ot_multiplier", 1.25)
                        regular_pay = total_hrs * regular_rate
                        ot_pay = ot_hrs * regular_rate * ot_multiplier
                        total_pay = regular_pay + ot_pay
                        
                        p1, p2, p3 = st.columns(3)
                        p1.metric("Regular Pay", f"₱{regular_pay:,.2f}")
                        p2.metric("Overtime Pay", f"₱{ot_pay:,.2f}")
                        p3.metric("Total Pay", f"₱{total_pay:,.2f}")
                    
                    # Download button
                    if not emp_df.empty:
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            emp_df.drop(columns=["id", "inserted_at", "name"]).to_excel(writer, index=False, sheet_name="Attendance")
                        output.seek(0)
                        
                        st.download_button(
                            label="Download this employee's records (Excel)",
                            data=output,
                            file_name=f"Attendance_{row['name']}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_{row['name']}"
                        )
                    
                    # Attendance History Table
                    if not emp_df.empty:
                        st.markdown("**Attendance History**")
                        
                        # Table with labels
                        display_df = emp_df[['date', 'time_in', 'time_out', 'total_hours', 'workload', 'remarks', 'overtime_hours']].copy()
                        display_df.columns = ['Date', 'Time In', 'Time Out', 'Total Hours', 'Workload', 'Remarks', 'Overtime']
                        
                        st.dataframe(
                            display_df,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Date": st.column_config.TextColumn("Date"),
                                "Time In": st.column_config.TextColumn("Time In"),
                                "Time Out": st.column_config.TextColumn("Time Out"),
                                "Total Hours": st.column_config.NumberColumn("Total Hours", format="%.1f"),
                                "Overtime": st.column_config.NumberColumn("Overtime", format="%.1f"),
                                "Workload": st.column_config.TextColumn("Workload", width="medium"),
                                "Remarks": st.column_config.TextColumn("Remarks", width="medium")
                            }
                        )
                        
                        # Actions per record
                        st.markdown("**Manage Records**")
                        for _, rec in emp_df.iterrows():
                            cols = st.columns([5, 1, 1])
                            cols[0].markdown(f"{rec['date']} • {rec['time_in']} – {rec['time_out']} ({rec['total_hours']:.1f} hrs)")
                            
                            if cols[1].button("✏️ Edit", key=f"edit_{rec['id']}"):
                                with st.form(f"edit_form_{rec['id']}"):
                                    c1, c2 = st.columns(2)
                                    with c1:
                                        new_in = st.time_input("Time In", 
                                            datetime.strptime(rec['time_in'], "%H:%M").time() if rec['time_in'] else time(8,0))
                                        new_out = st.time_input("Time Out", 
                                            datetime.strptime(rec['time_out'], "%H:%M").time() if rec['time_out'] else time(17,0))
                                    with c2:
                                        new_work = st.text_input("Workload", value=rec['workload'] or "")
                                        new_rem = st.text_area("Remarks", value=rec['remarks'] or "", height=80)
                                    
                                    if st.form_submit_button("Save Changes"):
                                        ti = new_in.strftime("%H:%M")
                                        to = new_out.strftime("%H:%M")
                                        success, msg = update_attendance_record(rec['id'], ti, to, new_work, new_rem)
                                        if success:
                                            st.success(msg)
                                            st.rerun()
                                        else:
                                            st.error(msg)
                            
                            if cols[2].button("🗑️ Delete", key=f"del_{rec['id']}"):
                                confirm_key = f"confirm_{rec['id']}"
                                if st.session_state.get(confirm_key, False):
                                    success, msg = delete_attendance_record(rec['id'])
                                    if success:
                                        st.success("Record deleted.")
                                        st.session_state.pop(confirm_key, None)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                                else:
                                    st.session_state[confirm_key] = True
                                    st.warning("Confirm delete this record? Click Delete again.")
                    
                    # Clear Attendance History (single confirmation)
                    if not emp_df.empty:
                        st.markdown("---")
                        clear_key = f"clear_{row['name']}"
                        if st.button("Clear Attendance History", key=clear_key):
                            confirm_clear = f"confirm_clear_{row['name']}"
                            if st.session_state.get(confirm_clear, False):
                                success, msg = clear_employee_attendance(row['name'])
                                if success:
                                    st.success(msg)
                                    st.session_state.pop(confirm_clear, None)
                                    st.rerun()
                                else:
                                    st.error(msg)
                            else:
                                st.session_state[confirm_clear] = True
                                st.warning("This will delete **all** attendance records for this employee. Click again to confirm.")
                
                # Delete Profile
                if st.button("Delete Profile", key=f"del_prof_{row['name']}"):
                    confirm_prof = f"confirm_prof_{row['name']}"
                    if st.session_state.get(confirm_prof, False):
                        success, msg = delete_employee(row['name'])
                        if success:
                            st.success(msg)
                            st.session_state.pop(confirm_prof, None)
                            # Remove from open expanders
                            st.session_state.open_expanders.discard(f"exp_{row['name']}")
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.session_state[confirm_prof] = True
                        st.warning(f"Delete **{row['name']}** profile and **all records**? Click again.")

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

elif page == "⚙️ Payroll Rates":
    st.subheader("Payroll Rates")
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