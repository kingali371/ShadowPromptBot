#!/usr/bin/env python3
"""
أداة رفع تلقائي إلى GitHub
"""

import subprocess
import sys
import os

def run_command(cmd):
    print(f"\n[*] تنفيذ: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[!] خطأ: {result.stderr}")
        return False
    print(result.stdout)
    return True

def main():
    print("""
    ╔══════════════════════════════════════╗
    ║   رفع Shadow Prompt Bot إلى GitHub   ║
    ╚══════════════════════════════════════╝
    """)
    
    # طلب معلومات المستخدم
    username = input("[?] اسم المستخدم في GitHub: ").strip()
    repo_name = input("[?] اسم المستودع (repo): ").strip()
    
    if not username or not repo_name:
        print("[!] الاسم والمستودع مطلوبان!")
        return
    
    repo_url = f"https://github.com/{username}/{repo_name}.git"
    
    # 1. تهيئة Git إذا لم تكن موجودة
    if not os.path.exists(".git"):
        print("\n[1] تهيئة مستودع Git...")
        run_command("git init")
    
    # 2. إضافة الملفات
    print("\n[2] إضافة الملفات...")
    run_command("git add .")
    
    # 3. عمل commit
    commit_msg = input("\n[?] رسالة الـ commit (مثال: 'الإصدار الأول'): ").strip()
    if not commit_msg:
        commit_msg = "Initial commit - Shadow Prompt Bot v3.0"
    run_command(f'git commit -m "{commit_msg}"')
    
    # 4. إضافة الـ remote
    print("\n[3] إضافة الـ remote...")
    run_command(f"git remote remove origin 2>/dev/null")
    run_command(f"git remote add origin {repo_url}")
    
    # 5. رفع إلى GitHub
    print("\n[4] رفع إلى GitHub...")
    run_command("git branch -M main")
    result = run_command("git push -u origin main")
    
    if result:
        print(f"\n✅ تم الرفع بنجاح!")
        print(f"🔗 رابط المستودع: https://github.com/{username}/{repo_name}")
    else:
        print("\n❌ فشل الرفع. تأكد من:")
        print("1. المستودع موجود مسبقاً على GitHub (أنشئه فارغاً)")
        print("2. لديك صلاحية push (SSH أو token)")
        print("3. اتصالك بالإنترنت")

if __name__ == "__main__":
    main()
