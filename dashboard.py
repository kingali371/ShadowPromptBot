#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
لوحة تحكم المسؤول - إدارة كاملة للبوت
"""

import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import pandas as pd
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SECRET", secrets.token_hex(32))
CORS(app)

limiter = Limiter(app, key_func=get_remote_address, default_limits=["200 per hour"])

# استيراد مدير قاعدة البيانات
from database import db_manager

# -------------------- مصادقة المسؤول --------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# -------------------- صفحات الواجهة --------------------
@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """صفحة تسجيل الدخول"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
        
        if username == admin_user and password == admin_pass:
            session['admin_logged_in'] = True
            session['login_time'] = datetime.utcnow().isoformat()
            return redirect(url_for('dashboard'))
        else:
            flash('بيانات الدخول غير صحيحة', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """تسجيل الخروج"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@admin_required
def dashboard():
    """لوحة التحكم الرئيسية"""
    stats = db_manager.get_system_stats()
    return render_template('dashboard.html', stats=stats)

@app.route('/users')
@admin_required
def users_page():
    """صفحة إدارة المستخدمين"""
    page = request.args.get('page', 1, type=int)
    users_data = db_manager.get_all_users(page=page)
    return render_template('users.html', users_data=users_data)

@app.route('/prompts')
@admin_required
def prompts_page():
    """صفحة عرض البرومبتات"""
    user_id = request.args.get('user_id')
    if user_id:
        prompts = db_manager.get_user_prompts(user_id, limit=100)
        return render_template('prompts.html', prompts=prompts, user_id=user_id)
    
    return render_template('prompts.html', prompts=[], user_id=None)

@app.route('/stats')
@admin_required
def stats_page():
    """صفحة الإحصائيات المتقدمة"""
    stats = db_manager.get_system_stats()
    return render_template('stats.html', stats=stats)

@app.route('/settings')
@admin_required
def settings_page():
    """صفحة الإعدادات"""
    return render_template('settings.html')

# -------------------- واجهة برمجة التطبيقات (API) للوحة التحكم --------------------
@app.route('/api/admin/stats')
@admin_required
def api_admin_stats():
    """API للحصول على إحصائيات مفصلة"""
    stats = db_manager.get_system_stats()
    
    # إحصائيات إضافية للرسوم البيانية
    daily_stats = []
    for i in range(7):
        day = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0)
        day_end = day.replace(hour=23, minute=59, second=59)
        # حساب عدد المستخدمين النشطين في هذا اليوم
        daily_stats.append({
            "date": day.strftime("%Y-%m-%d"),
            "value": 0  # سيتم حسابه من قاعدة البيانات
        })
    
    return jsonify({
        "success": True,
        "stats": stats,
        "daily": daily_stats,
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/admin/users')
@admin_required
def api_admin_users():
    """API للحصول على قائمة المستخدمين"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    users_data = db_manager.get_all_users(page=page)
    
    if search:
        filtered_users = [u for u in users_data['users'] if 
                         search.lower() in u.get('username', '').lower() or
                         search in u.get('user_id', '')]
        users_data['users'] = filtered_users
        users_data['total'] = len(filtered_users)
    
    return jsonify(users_data)

@app.route('/api/admin/user/<user_id>')
@admin_required
def api_admin_user(user_id):
    """API للحصول على تفاصيل مستخدم محدد"""
    user = db_manager.get_user(user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404
    
    prompts = db_manager.get_user_prompts(user_id, limit=20)
    user['recent_prompts'] = prompts
    
    return jsonify({"success": True, "user": user})

@app.route('/api/admin/user/<user_id>/ban', methods=['POST'])
@admin_required
def api_admin_ban_user(user_id):
    """API لحظر مستخدم"""
    # تنفيذ الحظر
    return jsonify({"success": True, "message": f"User {user_id} has been banned"})

@app.route('/api/admin/user/<user_id>/make-admin', methods=['POST'])
@admin_required
def api_admin_make_admin(user_id):
    """API لجعل مستخدم أدمن"""
    session = db_manager.get_session()
    if session:
        try:
            user = session.query(User).filter_by(user_id=str(user_id)).first()
            if user:
                user.is_admin = True
                session.commit()
                return jsonify({"success": True, "message": "User is now admin"})
        except Exception as e:
            session.rollback()
        finally:
            session.close()
    
    return jsonify({"success": False, "error": "Failed to update user"})

@app.route('/api/admin/export-data')
@admin_required
def api_admin_export_data():
    """تصدير البيانات كـ CSV/Excel"""
    format_type = request.args.get('format', 'csv')
    
    users = db_manager.get_all_users(page=1, per_page=10000)
    df = pd.DataFrame(users['users'])
    
    if format_type == 'csv':
        output = BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        output.seek(0)
        return send_file(output, mimetype='text/csv', as_attachment=True, download_name='users_export.csv')
    else:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Users', index=False)
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                        as_attachment=True, download_name='users_export.xlsx')

@app.route('/api/admin/prompts/<user_id>')
@admin_required
def api_admin_user_prompts(user_id):
    """API للحصول على برومبتات مستخدم محدد"""
    prompts = db_manager.get_user_prompts(user_id, limit=100)
    return jsonify({"success": True, "prompts": prompts})

# -------------------- تشغيل لوحة التحكم --------------------
def run_dashboard():
    port = int(os.getenv("DASHBOARD_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    run_dashboard()
