@echo off
title Shadow Prompt Bot Installer
echo 🔥 Shadow Prompt Bot - Installation
echo =====================================

echo [+] جاري تثبيت المكتبات...
pip install -r requirements.txt

echo [+] تم التثبيت بنجاح!
echo [*] لتشغيل البوت: python bot.py
set /p run="هل تريد تشغيل البوت الآن؟ (y/n): "
if /i "%run%"=="y" python bot.py
