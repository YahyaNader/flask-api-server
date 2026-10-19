from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt, datetime, sqlite3, requests, sys

app = Flask(__name__)
CORS(app)

SECRET_KEY = "your-super-secret-key-change-me"
ADMIN_KEY = "CHANGE_THIS_ADMIN_KEY"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1561140276293017772/F6LPnBa8ai5Nu0t7NwJWG-J_HUO9rR6WQfmv3_RHIA69h6-TSraeu5ZBNP9ccT96SKrR"
DB_FILE = "licenses.db"

def send_discord_notification(msg):
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
        except: pass

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, license_key TEXT UNIQUE NOT NULL, user_name TEXT, 
        created_at TEXT, expires_at TEXT, is_active INTEGER DEFAULT 1, max_devices INTEGER DEFAULT 1,
        message TEXT, last_known_time TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS activations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, license_key TEXT, hwid TEXT, device_name TEXT,
        activated_at TEXT, last_online TEXT, os_info TEXT, app_version TEXT,
        cpu_info TEXT, ram_info TEXT, disk_info TEXT, uptime_info TEXT, ip_address TEXT,
        gpu_info TEXT, laptop_model TEXT, mac_address TEXT, location TEXT, internet_speed TEXT, battery_status TEXT,
        app_open_count INTEGER DEFAULT 0, last_downloaded TEXT, total_downloaded_mb REAL DEFAULT 0, total_time_minutes INTEGER DEFAULT 0,
        is_killed INTEGER DEFAULT 0, UNIQUE(license_key, hwid)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS crash_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, hwid TEXT, error_msg TEXT, timestamp TEXT
    )""")
    
    cols = ["gpu_info", "laptop_model", "mac_address", "location", "internet_speed", "battery_status", 
            "app_open_count", "last_downloaded", "total_downloaded_mb", "total_time_minutes", "is_killed"]
    for col in cols:
        try: c.execute(f"ALTER TABLE activations ADD COLUMN {col} TEXT")
        except: pass
        
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/api/activate", methods=["POST"])
def activate():
    try:
        data = request.get_json() or {}
        license_key = data.get("license_key", "").strip()
        hwid = data.get("hwid", "").strip()
        device_name = data.get("device_name", "Unknown PC").strip()
        client_time_str = data.get("client_time", "")
        
        # ✨ بنشوف لو دي عملية تفعيل كاملة ولا مجرد فحص سريع
        is_full_activation = "os_info" in data

        os_info = data.get("os_info", "Unknown")
        app_version = data.get("app_version", "1.0.0")
        cpu_info = data.get("cpu_info", "Unknown")
        ram_info = data.get("ram_info", "Unknown")
        disk_info = data.get("disk_info", "Unknown")
        uptime_info = data.get("uptime_info", "Unknown")
        ip_address = data.get("ip_address", "Unknown")
        gpu_info = data.get("gpu_info", "Unknown")
        laptop_model = data.get("laptop_model", "Unknown")
        mac_address = data.get("mac_address", "Unknown")
        location = data.get("location", "Unknown")
        internet_speed = data.get("internet_speed", "Unknown")
        battery_status = data.get("battery_status", "Unknown")

        if not license_key or not hwid:
            return jsonify({"success": False, "message": "مفاتيح ناقصة"}), 400

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM licenses WHERE license_key = ?", (license_key,))
        lic = c.fetchone()

        if not lic:
            conn.close()
            return jsonify({"success": False, "message": "مفتاح غير صحيح"}), 401
            
        if not lic["is_active"]:
            conn.close()
            return jsonify({"success": False, "message": lic["message"] or "تم إيقاف هذا المفتاح."}), 403

        if client_time_str and lic["last_known_time"]:
            try:
                client_time = datetime.datetime.fromisoformat(client_time_str)
                last_time = datetime.datetime.fromisoformat(lic["last_known_time"])
                if client_time < last_time - datetime.timedelta(days=1):
                    conn.close()
                    return jsonify({"success": False, "message": "⚠️ خطأ في تاريخ الجهاز."}), 403
            except: pass

        if lic["expires_at"] and lic["expires_at"] != "2099-12-31T23:59:59":
            try:
                exp = datetime.datetime.fromisoformat(lic["expires_at"])
                if exp < datetime.datetime.now():
                    conn.close()
                    return jsonify({"success": False, "message": "انتهت صلاحية المفتاح."}), 403
            except: pass

        now_str = datetime.datetime.now().isoformat()
        c.execute("UPDATE licenses SET last_known_time = ? WHERE license_key = ?", (now_str, license_key))

        c.execute("SELECT COUNT(*) as cnt FROM activations WHERE license_key = ?", (license_key,))
        cnt = c.fetchone()["cnt"]
        c.execute("SELECT * FROM activations WHERE license_key = ? AND hwid = ?", (license_key, hwid))
        already = c.fetchone()

        if not already and cnt >= lic["max_devices"]:
            conn.close()
            return jsonify({"success": False, "message": f"وصلت للحد الأقصى ({lic['max_devices']} أجهزة)"}), 403

        if is_full_activation:
            if not already:
                c.execute("""INSERT INTO activations 
                             (license_key, hwid, device_name, activated_at, last_online, os_info, app_version, cpu_info, ram_info, disk_info, uptime_info, ip_address, gpu_info, laptop_model, mac_address, location, internet_speed, battery_status, app_open_count) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""", 
                          (license_key, hwid, device_name, now_str, now_str, os_info, app_version, cpu_info, ram_info, disk_info, uptime_info, ip_address, gpu_info, laptop_model, mac_address, location, internet_speed, battery_status))
            else:
                c.execute("""UPDATE activations 
                             SET last_online = ?, os_info = ?, app_version = ?, cpu_info = ?, ram_info = ?, disk_info = ?, uptime_info = ?, ip_address = ?, gpu_info = ?, laptop_model = ?, mac_address = ?, location = ?, internet_speed = ?, battery_status = ?, app_open_count = app_open_count + 1
                             WHERE license_key = ? AND hwid = ?""", 
                          (now_str, os_info, app_version, cpu_info, ram_info, disk_info, uptime_info, ip_address, gpu_info, laptop_model, mac_address, location, internet_speed, battery_status, license_key, hwid))
        else:
            if already:
                c.execute("UPDATE activations SET last_online = ? WHERE license_key = ? AND hwid = ?", (now_str, license_key, hwid))

        conn.commit()
        
        c.execute("SELECT is_killed FROM activations WHERE license_key = ? AND hwid = ?", (license_key, hwid))
        is_killed = c.fetchone()["is_killed"] if already else 0
        
        conn.close()
        
        if is_killed:
            return jsonify({"success": False, "message": "تم إغلاق البرنامج بواسطة الإدارة."}), 403
        
        token = jwt.encode({"license_key": license_key, "hwid": hwid, "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)}, SECRET_KEY, algorithm="HS256")
        return jsonify({"success": True, "token": token, "expires_at": lic["expires_at"], "message": "تم التفعيل بنجاح"})
    except Exception as e:
        print(e)
        return jsonify({"success": False, "message": "خطأ داخلي"}), 500

@app.route("/api/kill_device", methods=["POST"])
def kill_device():
    data = request.get_json() or {}
    hwid = data.get("hwid")
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE activations SET is_killed = 1 WHERE hwid = ?", (hwid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/crash_report", methods=["POST"])
def crash_report():
    data = request.get_json() or {}
    hwid = data.get("hwid")
    error_msg = data.get("error_msg", "Unknown Error")
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO crash_logs (hwid, error_msg, timestamp) VALUES (?, ?, ?)", (hwid, error_msg, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/verify", methods=["POST"])
def verify():
    data = request.get_json() or {}
    token = data.get("token", "")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return jsonify({"success": True, "payload": payload})
    except jwt.ExpiredSignatureError:
        return jsonify({"success": False, "message": "انتهت الجلسة"}), 401
    except Exception:
        return jsonify({"success": False, "message": "Token غير صحيح"}), 401

# ==========================================
# API للموقع (لوحة التحكم)
# ==========================================
def check_admin():
    return request.headers.get("X-Admin-Key") == ADMIN_KEY

@app.route("/api/admin/stats", methods=["GET"])
def admin_stats():
    if not check_admin(): return jsonify({"success": False}), 403
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM licenses")
        total_licenses = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) as cnt FROM activations")
        total_devices = c.fetchone()["cnt"]
        
        stats = []
        for i in range(6, -1, -1):
            day = datetime.datetime.now() - datetime.timedelta(days=i)
            day_str = day.strftime('%Y-%m-%d')
            c.execute("SELECT COUNT(*) as cnt FROM activations WHERE activated_at LIKE ?", (f"{day_str}%",))
            stats.append({"day": day.strftime('%m/%d'), "count": c.fetchone()["cnt"]})
            
        c.execute("""
            SELECT license_key, COUNT(hwid) as device_count 
            FROM activations 
            GROUP BY license_key 
            ORDER BY device_count DESC LIMIT 5
        """)
        top_keys = [{"key": r["license_key"], "count": r["device_count"]} for r in c.fetchall()]
        
        conn.close()
        return jsonify({"success": True, "total_licenses": total_licenses, "total_devices": total_devices, "chart_data": stats, "top_keys": top_keys})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/admin/list", methods=["GET"])
def admin_list():
    if not check_admin(): return jsonify({"success": False}), 403
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM licenses ORDER BY id DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    
    five_mins_ago = (datetime.datetime.now() - datetime.timedelta(minutes=5)).isoformat()
    for r in rows:
        conn = get_db()
        c2 = conn.cursor()
        c2.execute("SELECT COUNT(*) as cnt FROM activations WHERE license_key = ? AND last_online > ?", (r["license_key"], five_mins_ago))
        r["is_online"] = c2.fetchone()["cnt"] > 0
        conn.close()
    return jsonify({"success": True, "licenses": rows})

@app.route("/api/admin/devices", methods=["GET"])
def admin_devices():
    if not check_admin(): return jsonify({"success": False}), 403
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM activations ORDER BY last_online DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({"success": True, "devices": rows})

@app.route("/api/admin/device_details", methods=["POST"])
def admin_device_details():
    if not check_admin(): return jsonify({"success": False}), 403
    data = request.get_json() or {}
    hwid = data.get("hwid")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM activations WHERE hwid = ?", (hwid,))
    dev = c.fetchone()
    
    c.execute("SELECT * FROM crash_logs WHERE hwid = ? ORDER BY id DESC LIMIT 5", (hwid,))
    crashes = [dict(r) for r in c.fetchall()]
    
    conn.close()
    
    if dev:
        dev_dict = dict(dev)
        dev_dict['crashes'] = crashes
        return jsonify({"success": True, "device": dev_dict})
    return jsonify({"success": False, "message": "الجهاز غير موجود"}), 404

@app.route("/api/admin/create", methods=["POST"])
def admin_create():
    if not check_admin(): return jsonify({"success": False}), 403
    data = request.get_json() or {}
    key = data.get("license_key")
    if not key: return jsonify({"success": False, "message": "مفتاح مطلوب"}), 400
    duration = data.get("duration", "month")
    
    now = datetime.datetime.now()
    if duration == "week": expires = now + datetime.timedelta(days=7)
    elif duration == "month": expires = now + datetime.timedelta(days=30)
    elif duration == "year": expires = now + datetime.timedelta(days=365)
    else: expires = "2099-12-31T23:59:59"
    expires_str = expires.isoformat() if isinstance(expires, datetime.datetime) else expires

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO licenses (license_key, user_name, created_at, expires_at, max_devices) VALUES (?, ?, ?, ?, ?)", 
                  (key, data.get("user_name", ""), now.isoformat(), expires_str, data.get("max_devices", 1)))
        conn.commit()
        send_discord_notification(f"🔑 **مفتاح جديد!**\nالكود: `{key}`\nالمدة: `{duration}`")
        res = {"success": True}
    except sqlite3.IntegrityError:
        res = {"success": False, "message": "المفتاح موجود مسبقاً"}
    conn.close()
    return jsonify(res)

@app.route("/api/admin/edit", methods=["POST"])
def admin_edit():
    if not check_admin(): return jsonify({"success": False}), 403
    data = request.get_json() or {}
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE licenses SET user_name = ?, max_devices = ? WHERE license_key = ?", (data.get("user_name"), data.get("max_devices"), data.get("license_key")))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/delete_bulk", methods=["POST"])
def admin_delete_bulk():
    if not check_admin(): return jsonify({"success": False}), 403
    data = request.get_json() or {}
    keys = data.get("keys", [])
    if not keys: return jsonify({"success": True})
    
    conn = get_db()
    c = conn.cursor()
    for key in keys:
        c.execute("DELETE FROM licenses WHERE license_key = ?", (key,))
        c.execute("DELETE FROM activations WHERE license_key = ?", (key,))
        send_discord_notification(f"🗑 **تم حذف مفتاح!**\nالكود: `{key}`")
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/toggle", methods=["POST"])
def admin_toggle():
    if not check_admin(): return jsonify({"success": False}), 403
    data = request.get_json() or {}
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE licenses SET is_active = ? WHERE license_key = ?", (data.get("is_active"), data.get("license_key")))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/extend", methods=["POST"])
def admin_extend():
    if not check_admin(): return jsonify({"success": False}), 403
    data = request.get_json() or {}
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT expires_at FROM licenses WHERE license_key = ?", (data.get("license_key"),))
    row = c.fetchone()
    if row:
        try:
            exp = datetime.datetime.fromisoformat(row["expires_at"])
            new_exp = exp + datetime.timedelta(days=int(data.get("days", 30)))
            c.execute("UPDATE licenses SET expires_at = ? WHERE license_key = ?", (new_exp.isoformat(), data.get("license_key")))
            conn.commit()
        except: pass
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/message", methods=["POST"])
def admin_message():
    if not check_admin(): return jsonify({"success": False}), 403
    data = request.get_json() or {}
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE licenses SET message = ? WHERE license_key = ?", (data.get("message"), data.get("license_key")))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ==========================================
# الموقع (الواجهة)
# ==========================================
@app.route("/")
def home():
    html_content = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8"><title>لوحة التحكم</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, sans-serif; }
            body { background: #1e1e2e; color: #e0e0e0; padding: 20px; }
            .container { max-width: 1300px; margin: 0 auto; }
            h1 { color: #ff6b6b; margin-bottom: 20px; border-bottom: 2px solid #3a3a55; padding-bottom: 10px; display: flex; justify-content: space-between; align-items: center;}
            .btn { padding: 8px 15px; border-radius: 6px; border: none; background: #e63946; color: #fff; font-weight: bold; cursor: pointer; font-size: 14px;}
            .btn:hover { background: #ff4d5e; }
            .btn-sm { padding: 4px 8px; font-size: 12px; border-radius: 4px; margin: 2px; }
            .card { background: #2a2a3e; padding: 20px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #3a3a55; }
            .form-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr auto auto; gap: 10px; }
            input, select { padding: 10px; border-radius: 8px; border: 1px solid #3a3a55; background: #1e1e2e; color: #fff; width: 100%;}
            table { width: 100%; border-collapse: collapse; background: #1e1e2e; border-radius: 8px; }
            th, td { padding: 12px; text-align: right; border-bottom: 1px solid #3a3a55; font-size: 14px; cursor: pointer;}
            th { background: #2a2a3e; color: #aaa; user-select: none;}
            th:hover { color: #fff; }
            .active { color: #52b788; font-weight: bold; }
            .stopped { color: #ff6b6b; font-weight: bold; }
            
            .live-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #52b788; margin-left: 5px; box-shadow: 0 0 5px #52b788; animation: blink 1.5s infinite; }
            .offline-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #555; margin-left: 5px;}
            @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.2; } 100% { opacity: 1; } }
            
            .countdown-red { color: #ff6b6b; font-weight: bold; }
            .countdown-green { color: #52b788; }
            .search-box { margin-bottom: 15px; padding: 12px; background: #1e1e2e; border: 1px solid #3a3a55; color: #fff; border-radius: 8px; width: 100%; font-size: 16px;}
            input[type="checkbox"] { width: 18px; height: 18px; cursor: pointer; accent-color: #e63946; }
            
            .tabs { display: flex; margin-bottom: 20px; gap: 10px; flex-wrap: wrap;}
            .tab-btn { padding: 10px 20px; background: #3a3a55; color: #fff; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; transition: 0.2s; }
            .tab-btn.active { background: #e63946; }
            .tab-content { display: none; }
            .tab-content.active { display: block; }
            
            .stats-container { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap;}
            .stat-box { background: #1e1e2e; padding: 20px; border-radius: 8px; flex: 1; text-align: center; border: 1px solid #3a3a55; min-width: 200px;}
            .stat-box h3 { font-size: 32px; color: #e63946; margin-bottom: 5px; }
            .chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }

            #toast-container { position: fixed; top: 20px; left: 20px; z-index: 9999; display: flex; flex-direction: column; gap: 10px; }
            .toast { min-width: 250px; padding: 15px 20px; border-radius: 8px; color: #fff; font-weight: bold; box-shadow: 0 4px 12px rgba(0,0,0,0.3); opacity: 0; transform: translateY(-20px); transition: all 0.3s ease; display: flex; align-items: center; gap: 10px;}
            .toast.show { opacity: 1; transform: translateY(0); }
            .toast-success { background: #2d6a4f; border-right: 5px solid #52b788; }
            .toast-error { background: #c44536; border-right: 5px solid #ff6b6b; }
            .toast-info { background: #457b9d; border-right: 5px solid #a0e7e5; }
            
            .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.7); align-items: center; justify-content: center; }
            .modal-content { background-color: #2a2a3e; padding: 30px; border-radius: 12px; width: 600px; border: 1px solid #3a3a55; box-shadow: 0 10px 30px rgba(0,0,0,0.5); position: relative; max-height: 90vh; overflow-y: auto;}
            .modal-content h2 { color: #a0e7e5; margin-bottom: 20px; border-bottom: 1px solid #3a3a55; padding-bottom: 10px;}
            .modal-content .info-row { display: flex; justify-content: space-between; margin-bottom: 12px; font-size: 14px; }
            .modal-content .info-label { color: #aaa; }
            .modal-content .info-value { color: #fff; font-weight: bold; }
            .close-btn { position: absolute; top: 15px; left: 15px; font-size: 24px; color: #ff6b6b; cursor: pointer; }
            
            .specs-box { background: #1e1e2e; padding: 15px; border-radius: 8px; margin-top: 15px; display: flex; flex-wrap: wrap; justify-content: space-around; text-align: center; gap: 10px;}
            .spec-item { display: flex; flex-direction: column; gap: 5px; min-width: 100px; }
            .spec-item span:first-child { font-size: 20px; }
            .spec-item span:last-child { font-size: 12px; color: #aaa; }
            
            .btn-danger { background: #c44536; width: 100%; margin-top: 20px; padding: 12px; font-size: 16px; }
            .crash-log { background: #1e1e2e; padding: 10px; border-radius: 6px; margin-bottom: 8px; font-size: 12px; border-right: 3px solid #e63946; color: #ccc;}
        </style>
    </head>
    <body>
    <div id="toast-container"></div>

    <div class="container">
        <h1>🔑 لوحة تحكم المفاتيح</h1>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('keys')">المفاتيح</button>
            <button class="tab-btn" onclick="switchTab('devices')">الأجهزة المتصلة</button>
            <button class="tab-btn" onclick="switchTab('stats')">📊 الإحصائيات المتقدمة</button>
        </div>

        <div id="tab-keys" class="tab-content active">
            <div class="card">
                <div class="form-grid">
                    <input type="text" id="newKey" placeholder="الكود">
                    <input type="text" id="userName" placeholder="اسم المستخدم">
                    <select id="duration">
                        <option value="week">أسبوع</option>
                        <option value="month" selected>شهر</option>
                        <option value="year">سنة</option>
                        <option value="lifetime">مدى الحياة</option>
                    </select>
                    <input type="number" id="maxDevices" value="1" title="عدد الأجهزة">
                    <button class="btn" onclick="generateKey()">🎲 توليد</button>
                    <button class="btn" onclick="createKey()">إضافة</button>
                </div>
            </div>

            <div class="card">
                <div style="display: flex; justify-content: space-between; margin-bottom: 15px;">
                    <input type="text" id="searchBar" class="search-box" placeholder="🔍 بحث بالكود أو اسم المستخدم..." onkeyup="renderTable()" style="width: 70%;">
                    <button class="btn" style="background:#c44536;" onclick="deleteSelected()">🗑 حذف المحدد</button>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th style="width: 40px;"><input type="checkbox" id="selectAll" onclick="toggleAll(this)"></th>
                            <th onclick="sortTable('license_key')">المفتاح ↕️</th>
                            <th onclick="sortTable('user_name')">المستخدم ↕️</th>
                            <th onclick="sortTable('is_online')">الحالة ↕️</th>
                            <th onclick="sortTable('max_devices')">الأجهزة ↕️</th>
                            <th onclick="sortTable('expires_at')">الانتهاء ↕️</th>
                            <th>إجراءات</th>
                        </tr>
                    </thead>
                    <tbody id="keysTable"></tbody>
                </table>
            </div>
        </div>

        <div id="tab-devices" class="tab-content">
            <div class="card">
                <h2>الأجهزة المتصلة حديثاً (اضغط على أي جهاز لمعرفة تفاصيله)</h2>
                <table>
                    <thead><tr><th>اسم الجهاز</th><th>HWID</th><th>المفتاح</th><th>آخر اتصال</th></tr></thead>
                    <tbody id="devicesTable"></tbody>
                </table>
            </div>
        </div>

        <div id="tab-stats" class="tab-content">
            <div class="stats-container">
                <div class="stat-box"><h3 id="totalLics">0</h3><p>إجمالي المفاتيح</p></div>
                <div class="stat-box"><h3 id="totalDevs">0</h3><p>الأجهزة المفعّلة</p></div>
            </div>
            <div class="chart-grid">
                <div class="card">
                    <h2>📈 التفعيلات في آخر 7 أيام</h2>
                    <canvas id="myChart"></canvas>
                </div>
                <div class="card">
                    <h2>🏆 أكتر 5 مفاتيح استخداماً</h2>
                    <canvas id="topKeysChart"></canvas>
                </div>
            </div>
        </div>
    </div>

    <div id="deviceModal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="closeModal()">&times;</span>
            <h2>💻 تفاصيل الجهاز</h2>
            <div class="info-row"><span class="info-label">اسم الجهاز:</span> <span class="info-value" id="m_device_name">-</span></div>
            <div class="info-row"><span class="info-label">نظام التشغيل:</span> <span class="info-value" id="m_os">-</span></div>
            <div class="info-row"><span class="info-label">موديل الجهاز:</span> <span class="info-value" id="m_model">-</span></div>
            <div class="info-row"><span class="info-label">المفتاح:</span> <span class="info-value" id="m_key">-</span></div>
            <div class="info-row"><span class="info-label">تاريخ التفعيل الأول:</span> <span class="info-value" id="m_activated">-</span></div>
            <div class="info-row"><span class="info-label">آخر اتصال:</span> <span class="info-value" id="m_last_online">-</span></div>
            
            <div class="specs-box">
                <div class="spec-item"><span>🧠</span> <span id="m_cpu">-</span> <span>المعالج</span></div>
                <div class="spec-item"><span>🎮</span> <span id="m_gpu">-</span> <span>كرت الشاشة</span></div>
                <div class="spec-item"><span>⚡</span> <span id="m_ram">-</span> <span>الرامات</span></div>
                <div class="spec-item"><span>💾</span> <span id="m_disk">-</span> <span>الهارد ديسك</span></div>
                <div class="spec-item"><span>🔋</span> <span id="m_battery">-</span> <span>البطارية</span></div>
                <div class="spec-item"><span>🌐</span> <span id="m_speed">-</span> <span>سرعة النت</span></div>
            </div>
            
            <div class="info-row" style="margin-top: 15px;"><span class="info-label">وقت التشغيل:</span> <span class="info-value" id="m_uptime">-</span></div>
            <div class="info-row"><span class="info-label">الـ IP Address:</span> <span class="info-value" id="m_ip">-</span></div>
            <div class="info-row"><span class="info-label">الدولة:</span> <span class="info-value" id="m_location">-</span></div>
            <div class="info-row"><span class="info-label">الـ MAC Address:</span> <span class="info-value" id="m_mac" style="font-size: 11px;">-</span></div>
            
            <div class="info-row" style="margin-top: 20px;"><span class="info-label">HWID (بصمة الجهاز):</span> <span class="info-value" id="m_hwid" style="font-size:12px; word-break: break-all;">-</span></div>
            
            <h3 style="margin-top: 20px; font-size: 14px; color: #e63946;">📊 الاستخدام</h3>
            <div class="info-row"><span class="info-label">عدد مرات فتح البرنامج:</span> <span class="info-value" id="m_opens">-</span></div>
            <div class="info-row"><span class="info-label">آخر فيديو اتحمّل:</span> <span class="info-value" id="m_last_down">-</span></div>
            
            <h3 style="margin-top: 20px; font-size: 14px; color: #e63946;">🐞 سجل الأخطاء (آخر 5)</h3>
            <div id="m_crashes"></div>
            
            <button class="btn btn-danger" onclick="killDevice()">💀 إغلاق البرنامج فوراً على هذا الجهاز</button>
        </div>
    </div>

    <script>
        const ADMIN_KEY = "CHANGE_THIS_ADMIN_KEY"; 
        const API_URL = "/api/admin"; 
        let allLicenses = [];
        let sortAsc = true;
        let currentSort = "";
        let chartInstance = null;
        let topKeysChartInstance = null;
        let currentHwid = "";

        function showToast(message, type = 'info') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            let icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : 'ℹ️');
            toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
            container.appendChild(toast);
            setTimeout(() => toast.classList.add('show'), 100);
            setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 3000);
        }

        function switchTab(tabName) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('tab-' + tabName).classList.add('active');
            if(tabName === 'keys') loadData();
            else if(tabName === 'devices') loadDevices();
            else if(tabName === 'stats') loadStats();
        }

        async function loadStats() {
            const res = await fetch(`${API_URL}/stats`, { headers: { "X-Admin-Key": ADMIN_KEY } });
            const data = await res.json();
            if(!data.success) return;
            document.getElementById('totalLics').innerText = data.total_licenses;
            document.getElementById('totalDevs').innerText = data.total_devices;
            const labels = data.chart_data.map(d => d.day);
            const values = data.chart_data.map(d => d.count);
            if(chartInstance) chartInstance.destroy();
            const ctx1 = document.getElementById('myChart').getContext('2d');
            chartInstance = new Chart(ctx1, {
                type: 'line',
                data: { labels: labels, datasets: [{ label: 'عدد الأجهزة المفعّلة', data: values, borderColor: '#e63946', backgroundColor: 'rgba(230, 57, 70, 0.2)', fill: true, tension: 0.4 }] },
                options: { responsive: true, plugins: { legend: { labels: { color: '#fff' } } }, scales: { x: { ticks: { color: '#aaa' } }, y: { ticks: { color: '#aaa' } } } }
            });
            const topKeys = data.top_keys || [];
            const topLabels = topKeys.map(k => k.key);
            const topValues = topKeys.map(k => k.count);
            if(topKeysChartInstance) topKeysChartInstance.destroy();
            const ctx2 = document.getElementById('topKeysChart').getContext('2d');
            topKeysChartInstance = new Chart(ctx2, {
                type: 'bar',
                data: { labels: topLabels, datasets: [{ label: 'عدد الأجهزة', data: topValues, backgroundColor: '#52b788' }] },
                options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#aaa' } }, y: { ticks: { color: '#aaa' } } } }
            });
        }

        async function loadData() {
            const res = await fetch(`${API_URL}/list`, { headers: { "X-Admin-Key": ADMIN_KEY } });
            const data = await res.json();
            if(data.success) { allLicenses = data.licenses; renderTable(); }
        }

        async function loadDevices() {
            const res = await fetch(`${API_URL}/devices`, { headers: { "X-Admin-Key": ADMIN_KEY } });
            const data = await res.json();
            const tbody = document.getElementById('devicesTable');
            tbody.innerHTML = '';
            if (data.devices.length === 0) { tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;">لا توجد أجهزة</td></tr>'; return; }
            const now = new Date();
            data.devices.forEach(dev => {
                let timeText = '-';
                let liveDot = '<span class="offline-dot"></span>';
                if (dev.last_online) {
                    const lastDate = new Date(dev.last_online);
                    const diffMins = Math.floor((now - lastDate) / 1000 / 60);
                    if (diffMins < 1) timeText = "الآن";
                    else if (diffMins < 60) timeText = `منذ ${diffMins} دقيقة`;
                    else timeText = lastDate.toLocaleTimeString('ar-EG', {hour: '2-digit', minute:'2-digit'});
                    if (diffMins <= 5) { liveDot = '<span class="live-dot" title="متصل الآن"></span>'; timeText = "متصل الآن 🟢"; }
                }
                tbody.innerHTML += `
                    <tr onclick="openDeviceDetails('${dev.hwid}')" style="cursor:pointer;">
                        <td>${liveDot} ${dev.device_name || 'Unknown'}</td>
                        <td>${dev.hwid.substring(0, 10)}...</td>
                        <td>${dev.license_key}</td>
                        <td style="font-size:12px; color:#aaa;">${timeText}</td>
                    </tr>
                `;
            });
        }

        async function openDeviceDetails(hwid) {
            currentHwid = hwid;
            try {
                const res = await fetch(`${API_URL}/device_details`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY },
                    body: JSON.stringify({ hwid: hwid })
                });
                const data = await res.json();
                if(data.success) {
                    const d = data.device;
                    document.getElementById('m_device_name').innerText = d.device_name || 'Unknown';
                    document.getElementById('m_os').innerText = d.os_info || 'غير معروف';
                    document.getElementById('m_model').innerText = d.laptop_model || 'غير معروف';
                    document.getElementById('m_key').innerText = d.license_key;
                    document.getElementById('m_activated').innerText = new Date(d.activated_at).toLocaleString('ar-EG');
                    document.getElementById('m_last_online').innerText = new Date(d.last_online).toLocaleString('ar-EG');
                    
                    document.getElementById('m_cpu').innerText = d.cpu_info || 'غير معروف';
                    document.getElementById('m_gpu').innerText = d.gpu_info || 'غير معروف';
                    document.getElementById('m_ram').innerText = d.ram_info || 'غير معروف';
                    document.getElementById('m_disk').innerText = d.disk_info || 'غير معروف';
                    document.getElementById('m_battery').innerText = d.battery_status || 'غير معروف';
                    document.getElementById('m_speed').innerText = d.internet_speed || 'غير معروف';
                    
                    document.getElementById('m_uptime').innerText = d.uptime_info || 'غير معروف';
                    document.getElementById('m_ip').innerText = d.ip_address || 'غير معروف';
                    document.getElementById('m_location').innerText = d.location || 'غير معروف';
                    document.getElementById('m_mac').innerText = d.mac_address || 'غير معروف';
                    
                    document.getElementById('m_opens').innerText = d.app_open_count || 0;
                    document.getElementById('m_last_down').innerText = d.last_downloaded || 'لا يوجد';
                    
                    const crashesDiv = document.getElementById('m_crashes');
                    crashesDiv.innerHTML = '';
                    if (d.crashes && d.crashes.length > 0) {
                        d.crashes.forEach(c => {
                            crashesDiv.innerHTML += `<div class="crash-log"><b>${new Date(c.timestamp).toLocaleString('ar-EG')}</b><br>${c.error_msg}</div>`;
                        });
                    } else {
                        crashesDiv.innerHTML = '<div style="color:#aaa; font-size:12px;">لا توجد أخطاء مسجلة</div>';
                    }
                    
                    document.getElementById('m_hwid').innerText = d.hwid;
                    
                    document.getElementById('deviceModal').style.display = 'flex';
                }
            } catch(e) {}
        }

        async function killDevice() {
            if (!confirm("هل أنت متأكد من إغلاق البرنامج فوراً على هذا الجهاز؟")) return;
            
            await fetch(`/api/kill_device`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ hwid: currentHwid })
            });
            showToast("تم إرسال أمر الإغلاق للجهاز", "success");
            closeModal();
        }

        function closeModal() { document.getElementById('deviceModal').style.display = 'none'; }

        function toggleAll(source) { document.querySelectorAll('.row-checkbox').forEach(cb => cb.checked = source.checked); }

        function renderTable() {
            const tbody = document.getElementById('keysTable');
            const query = document.getElementById('searchBar').value.toLowerCase();
            tbody.innerHTML = '';
            let filtered = allLicenses.filter(l => l.license_key.toLowerCase().includes(query) || (l.user_name && l.user_name.toLowerCase().includes(query)));
            if (currentSort) {
                filtered.sort((a, b) => {
                    let valA = a[currentSort] || ""; let valB = b[currentSort] || "";
                    if (typeof valA === 'string') valA = valA.toLowerCase();
                    if (typeof valB === 'string') valB = valB.toLowerCase();
                    if (valA < valB) return sortAsc ? -1 : 1; if (valA > valB) return sortAsc ? 1 : -1; return 0;
                });
            }
            if (filtered.length === 0) { tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">لا توجد نتائج</td></tr>'; return; }
            filtered.forEach(lic => {
                const isAct = lic.is_active ? '<span class="active">يعمل</span>' : '<span class="stopped">موقوف</span>';
                const onlineDot = lic.is_online ? '<span class="live-dot"></span>' : '<span class="offline-dot"></span>';
                let daysLeftText = "مدى الحياة"; let daysClass = "countdown-green";
                if (lic.expires_at && lic.expires_at !== "2099-12-31T23:59:59") {
                    const expDate = new Date(lic.expires_at); const now = new Date();
                    const diffTime = expDate - now; const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                    if (diffDays <= 0) { daysLeftText = "منتهي"; daysClass = "countdown-red"; }
                    else { daysLeftText = `متبقي ${diffDays} يوم`; daysClass = diffDays <= 7 ? "countdown-red" : "countdown-green"; }
                }
                const toggleTxt = lic.is_active ? 'إيقاف' : 'تشغيل';
                const toggleStyle = lic.is_active ? 'background: #f4a261; color: #000;' : 'background: #52b788; color: #000;';
                tbody.innerHTML += `
                    <tr>
                        <td><input type="checkbox" class="row-checkbox" value="${lic.license_key}"></td>
                        <td><b>${lic.license_key}</b> <button class="btn-sm" style="background:#457b9d;" onclick="copyKey('${lic.license_key}')" title="نسخ">📋</button></td>
                        <td>${lic.user_name || '-'}</td>
                        <td>${isAct} ${onlineDot}</td>
                        <td>${lic.max_devices}</td>
                        <td class="${daysClass}">${daysLeftText}</td>
                        <td>
                            <button class="btn-sm" style="${toggleStyle}" onclick="toggleKey('${lic.license_key}', ${lic.is_active ? 0 : 1})">${toggleTxt}</button>
                            <button class="btn-sm" style="background:#457b9d;" onclick="extendKey('${lic.license_key}')">+ شهر</button>
                            <button class="btn-sm" style="background:#9d4edd;" onclick="editKey('${lic.license_key}', '${lic.user_name || ''}', ${lic.max_devices})">✏️ تعديل</button>
                            <button class="btn-sm" style="background:#c44536;" onclick="setMessage('${lic.license_key}')">💬 رسالة</button>
                        </td>
                    </tr>
                `;
            });
        }

        function sortTable(column) { if (currentSort === column) sortAsc = !sortAsc; else { currentSort = column; sortAsc = true; } renderTable(); }
        function generateKey() { const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"; let key = "VDP-"; for(let i=0; i<4; i++) { for(let j=0; j<4; j++) key += chars.charAt(Math.floor(Math.random() * chars.length)); if(i < 3) key += "-"; } document.getElementById('newKey').value = key; }
        function copyKey(key) { navigator.clipboard.writeText(key); showToast(`تم نسخ المفتاح: ${key}`, "info"); }
        async function createKey() { const key = document.getElementById('newKey').value; if (!key) return showToast("اكتب أو ولد الكود أولاً", "error"); const res = await fetch(`${API_URL}/create`, { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY }, body: JSON.stringify({ license_key: key, user_name: document.getElementById('userName').value, max_devices: document.getElementById('maxDevices').value, duration: document.getElementById('duration').value }) }); const data = await res.json(); if(data.success) { showToast("تمت إضافة المفتاح بنجاح", "success"); document.getElementById('newKey').value = ''; loadData(); } else { showToast(data.message || "حدث خطأ", "error"); } }
        async function deleteSelected() { const checked = Array.from(document.querySelectorAll('.row-checkbox:checked')).map(cb => cb.value); if(checked.length === 0) return showToast("حدد مفاتيح أولاً", "error"); if(!confirm(`هل أنت متأكد من حذف ${checked.length} مفتاح؟`)) return; await fetch(`${API_URL}/delete_bulk`, { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY }, body: JSON.stringify({ keys: checked }) }); showToast("تم حذف المفاتيح المحددة", "success"); loadData(); }
        async function extendKey(key) { if (!confirm("هل تريد إضافة 30 يوم؟")) return; await fetch(`${API_URL}/extend`, { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY }, body: JSON.stringify({ license_key: key, days: 30 }) }); showToast("تم تمديد المفتاح 30 يوم", "success"); loadData(); }
        async function toggleKey(key, state) { await fetch(`${API_URL}/toggle`, { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY }, body: JSON.stringify({ license_key: key, is_active: state }) }); showToast(state === 0 ? "تم إيقاف المفتاح" : "تم تشغيل المفتاح", "info"); loadData(); }
        async function editKey(key, oldName, oldDevs) { const newName = prompt("اسم المستخدم الجديد:", oldName); if (newName === null) return; const newDevs = prompt("عدد الأجهزة الجديد:", oldDevs); if (newDevs === null) return; await fetch(`${API_URL}/edit`, { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY }, body: JSON.stringify({ license_key: key, user_name: newName, max_devices: newDevs }) }); showToast("تم التعديل بنجاح", "success"); loadData(); }
        async function setMessage(key) { const msg = prompt("اكتب الرسالة للمستخدم:"); if (msg === null) return; await fetch(`${API_URL}/message`, { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY }, body: JSON.stringify({ license_key: key, message: msg }) }); showToast("تم حفظ الرسالة", "success"); }
        window.onload = () => { loadData(); setInterval(loadData, 30000); };
    </script>
    </body>
    </html>
    """
    return html_content

if __name__ == "__main__":
    try:
        init_db()
        print("🚀 السيرفر شغال على http://localhost:5000")
        app.run(host="0.0.0.0", port=5000, debug=True)
    except Exception as e:
        print(f"❌ فشل تشغيل السيرفر: {e}")
        import traceback
        traceback.print_exc()
        input("اضغط Enter للخروج...")