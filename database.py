#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
إدارة قواعد البيانات: PostgreSQL (رئيسية) + MongoDB (نسخ احتياطي)
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, BigInteger, Boolean, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.pool import NullPool
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

Base = declarative_base()

# -------------------- نماذج PostgreSQL --------------------
class User(Base):
    """نموذج المستخدم"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), unique=True, nullable=False, index=True)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    language = Column(String(5), default='ar')
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    total_prompts = Column(Integer, default=0)
    premium_until = Column(DateTime, nullable=True)
    
    # العلاقات
    prompts = relationship("PromptHistory", back_populates="user")
    sessions = relationship("UserSession", back_populates="user")

class PromptHistory(Base):
    """سجل البرومبتات"""
    __tablename__ = 'prompts_history'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), ForeignKey('users.user_id'), nullable=False, index=True)
    prompt_text = Column(Text, nullable=False)
    prompt_type = Column(String(50))  # hack, code, break, creative, custom
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # العلاقات
    user = relationship("User", back_populates="prompts")

class UserSession(Base):
    """جلسات المستخدمين"""
    __tablename__ = 'user_sessions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), ForeignKey('users.user_id'), nullable=False)
    session_token = Column(String(255), unique=True)
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="sessions")

class SystemStats(Base):
    """إحصائيات النظام"""
    __tablename__ = 'system_stats'
    
    id = Column(Integer, primary_key=True)
    stat_key = Column(String(100), unique=True, index=True)
    stat_value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class APILog(Base):
    """سجل طلبات API"""
    __tablename__ = 'api_logs'
    
    id = Column(Integer, primary_key=True)
    endpoint = Column(String(200))
    method = Column(String(10))
    ip_address = Column(String(45))
    status_code = Column(Integer)
    response_time = Column(Float)  # milliseconds
    created_at = Column(DateTime, default=datetime.utcnow)

class DatabaseManager:
    """مدير قواعد البيانات المتكامل"""
    
    def __init__(self):
        self.postgres_engine = None
        self.postgres_session = None
        self.mongo_client = None
        self.mongo_db = None
        self.use_mongo_backup = False
        
        self._init_postgres()
        self._init_mongo()
    
    def _init_postgres(self):
        """تهيئة PostgreSQL"""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL غير موجود!")
            return
        
        try:
            self.postgres_engine = create_engine(
                database_url,
                poolclass=NullPool,
                pool_pre_ping=True
            )
            Base.metadata.create_all(self.postgres_engine)
            self.postgres_session = sessionmaker(bind=self.postgres_engine)
            logger.info("✅ PostgreSQL متصل بنجاح")
        except Exception as e:
            logger.error(f"خطأ في PostgreSQL: {e}")
            self.postgres_engine = None
    
    def _init_mongo(self):
        """تهيئة MongoDB كنسخة احتياطية"""
        mongodb_uri = os.getenv("MONGODB_URI")
        if not mongodb_uri:
            return
        
        try:
            self.mongo_client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
            self.mongo_client.admin.command('ping')
            self.mongo_db = self.mongo_client[os.getenv("DATABASE_NAME", "shadow_prompt_bot")]
            self.use_mongo_backup = True
            logger.info("✅ MongoDB متصل (نسخة احتياطية)")
        except Exception as e:
            logger.warning(f"MongoDB غير متصل: {e}")
    
    def get_session(self) -> Optional[Session]:
        """الحصول على جلسة PostgreSQL"""
        if self.postgres_session:
            return self.postgres_session()
        return None
    
    # -------------------- عمليات المستخدم --------------------
    def create_or_update_user(self, user_id: str, username: str = None, 
                               first_name: str = None, language: str = 'ar') -> Dict:
        """إنشاء أو تحديث مستخدم"""
        session = self.get_session()
        if not session:
            return self._mongo_create_user(user_id, username, first_name, language)
        
        try:
            user = session.query(User).filter_by(user_id=str(user_id)).first()
            if user:
                user.last_active = datetime.utcnow()
                user.username = username or user.username
                user.first_name = first_name or user.first_name
            else:
                user = User(
                    user_id=str(user_id),
                    username=username,
                    first_name=first_name,
                    language=language,
                    created_at=datetime.utcnow(),
                    last_active=datetime.utcnow()
                )
                session.add(user)
            
            session.commit()
            
            # نسخ احتياطي في MongoDB
            self._backup_to_mongo("users", user_id, {
                "user_id": str(user_id),
                "username": username,
                "first_name": first_name,
                "language": language,
                "last_active": datetime.utcnow()
            })
            
            return {
                "user_id": user.user_id,
                "username": user.username,
                "first_name": user.first_name,
                "language": user.language,
                "is_admin": user.is_admin
            }
        except Exception as e:
            session.rollback()
            logger.error(f"خطأ في إنشاء المستخدم: {e}")
            return None
        finally:
            session.close()
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        """الحصول على مستخدم"""
        session = self.get_session()
        if session:
            try:
                user = session.query(User).filter_by(user_id=str(user_id)).first()
                if user:
                    return {
                        "user_id": user.user_id,
                        "username": user.username,
                        "first_name": user.first_name,
                        "language": user.language,
                        "is_active": user.is_active,
                        "is_admin": user.is_admin,
                        "total_prompts": user.total_prompts,
                        "created_at": user.created_at,
                        "last_active": user.last_active
                    }
            except Exception as e:
                logger.error(f"خطأ في جلب المستخدم: {e}")
            finally:
                session.close()
        
        # محاولة من MongoDB
        return self._mongo_get_user(user_id)
    
    def update_prompt(self, user_id: str, new_prompt: str, prompt_type: str = 'custom') -> bool:
        """تحديث البرومبت الحالي للمستخدم"""
        session = self.get_session()
        if session:
            try:
                user = session.query(User).filter_by(user_id=str(user_id)).first()
                if not user:
                    self.create_or_update_user(user_id)
                    user = session.query(User).filter_by(user_id=str(user_id)).first()
                
                # حفظ في سجل البرومبتات
                history = PromptHistory(
                    user_id=str(user_id),
                    prompt_text=new_prompt,
                    prompt_type=prompt_type,
                    created_at=datetime.utcnow()
                )
                session.add(history)
                
                # تحديث عدد البرومبتات
                user.total_prompts += 1
                user.last_active = datetime.utcnow()
                
                session.commit()
                
                # نسخ احتياطي في MongoDB
                self._backup_to_mongo("prompts_history", f"{user_id}_{datetime.utcnow().timestamp()}", {
                    "user_id": str(user_id),
                    "prompt": new_prompt,
                    "type": prompt_type,
                    "created_at": datetime.utcnow()
                })
                
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"خطأ في تحديث البرومبت: {e}")
                return False
            finally:
                session.close()
        return False
    
    def get_user_prompts(self, user_id: str, limit: int = 50) -> List[Dict]:
        """الحصول على سجل برومبتات المستخدم"""
        session = self.get_session()
        if session:
            try:
                prompts = session.query(PromptHistory).filter_by(
                    user_id=str(user_id)
                ).order_by(PromptHistory.created_at.desc()).limit(limit).all()
                
                return [
                    {
                        "id": p.id,
                        "prompt": p.prompt_text,
                        "type": p.prompt_type,
                        "created_at": p.created_at
                    }
                    for p in prompts
                ]
            except Exception as e:
                logger.error(f"خطأ في جلب البرومبتات: {e}")
            finally:
                session.close()
        return []
    
    def get_all_users(self, page: int = 1, per_page: int = 20) -> Dict:
        """الحصول على جميع المستخدمين مع ترقيم"""
        session = self.get_session()
        if session:
            try:
                query = session.query(User).filter_by(is_active=True)
                total = query.count()
                
                users = query.order_by(User.last_active.desc()).offset(
                    (page - 1) * per_page
                ).limit(per_page).all()
                
                return {
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "users": [
                        {
                            "user_id": u.user_id,
                            "username": u.username,
                            "first_name": u.first_name,
                            "language": u.language,
                            "total_prompts": u.total_prompts,
                            "last_active": u.last_active,
                            "is_admin": u.is_admin
                        }
                        for u in users
                    ]
                }
            except Exception as e:
                logger.error(f"خطأ في جلب المستخدمين: {e}")
            finally:
                session.close()
        return {"total": 0, "page": 1, "per_page": per_page, "users": []}
    
    def get_system_stats(self) -> Dict:
        """الحصول على إحصائيات النظام"""
        session = self.get_session()
        stats = {
            "total_users": 0,
            "total_prompts": 0,
            "active_today": 0,
            "active_week": 0,
            "languages": {"ar": 0, "en": 0, "fr": 0},
            "prompts_by_type": {"hack": 0, "code": 0, "break": 0, "creative": 0, "custom": 0}
        }
        
        if session:
            try:
                stats["total_users"] = session.query(User).filter_by(is_active=True).count()
                stats["total_prompts"] = session.query(PromptHistory).count()
                
                # المستخدمون النشطون اليوم
                today = datetime.utcnow().replace(hour=0, minute=0, second=0)
                stats["active_today"] = session.query(User).filter(
                    User.last_active >= today
                ).count()
                
                # المستخدمون النشطون الأسبوع
                week_ago = datetime.utcnow() - timedelta(days=7)
                stats["active_week"] = session.query(User).filter(
                    User.last_active >= week_ago
                ).count()
                
                # توزيع اللغات
                lang_stats = session.query(User.language, func.count()).group_by(User.language).all()
                for lang, count in lang_stats:
                    stats["languages"][lang] = count
                
                # توزيع أنواع البرومبتات
                type_stats = session.query(PromptHistory.prompt_type, func.count()).group_by(
                    PromptHistory.prompt_type
                ).all()
                for ptype, count in type_stats:
                    if ptype in stats["prompts_by_type"]:
                        stats["prompts_by_type"][ptype] = count
                
            except Exception as e:
                logger.error(f"خطأ في جلب الإحصائيات: {e}")
            finally:
                session.close()
        
        return stats
    
    def _backup_to_mongo(self, collection: str, doc_id: str, data: Dict):
        """نسخ احتياطي إلى MongoDB"""
        if not self.use_mongo_backup:
            return
        
        try:
            col = self.mongo_db[collection]
            col.update_one({"_id": doc_id}, {"$set": data}, upsert=True)
        except Exception as e:
            logger.warning(f"فشل النسخ الاحتياطي لـ MongoDB: {e}")
    
    def _mongo_create_user(self, user_id, username, first_name, language):
        """إنشاء مستخدم في MongoDB (بديل)"""
        # تنفيذ مبسط...
        pass
    
    def _mongo_get_user(self, user_id):
        """جلب مستخدم من MongoDB"""
        # تنفيذ مبسط...
        return None

# -------------------- إنشاء المدير العالمي --------------------
db_manager = DatabaseManager()
