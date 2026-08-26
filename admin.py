import json
import os
import shutil
from pathlib import Path
from typing import List
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from config import Config
from utils import logger, format_size

CHANNELS_FILE = Path(Config.TEMP_DIR).parent / "channels.json"
ADD_CHANNEL = 10

class AdminSystem:
    @staticmethod
    def load_channels() -> List[str]:
        try:
            if CHANNELS_FILE.exists():
                with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            return []
        except Exception:
            return []
    
    @staticmethod
    def save_channels(channels: List[str]) -> bool:
        try:
            with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
                json.dump(channels, f, ensure_ascii=False, indent=2)
            Config.FORCED_CHANNELS = channels
            return True
        except Exception:
            return False
    
    @staticmethod
    def is_admin(user_id: int) -> bool:
        return user_id in Config.ADMINS
    
    @staticmethod
    def get_all_channels() -> List[str]:
        channels = [Config.FORCED_CHANNEL] if Config.FORCED_CHANNEL else []
        channels += Config.FORCED_CHANNELS
        return list(dict.fromkeys(channels))

def get_system_stats() -> dict:
    try:
        disk_usage = shutil.disk_usage("/")
        temp_files = list(Path(Config.TEMP_DIR).glob("*"))
        temp_size = sum(f.stat().st_size for f in temp_files if f.is_file())
        
        from main import user_sessions
        active_sessions = len(user_sessions)
        
        return {
            "disk_total": disk_usage.total,
            "disk_used": disk_usage.used,
            "disk_free": disk_usage.free,
            "disk_percent": (disk_usage.used / disk_usage.total) * 100,
            "temp_files": len(temp_files),
            "temp_size": temp_size,
            "active_sessions": active_sessions,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        logger.error(f"❌ فشل الحصول على الإحصائيات: {e}")
        return {"error": str(e)}

def clean_temp_files() -> dict:
    try:
        temp_path = Path(Config.TEMP_DIR)
        if not temp_path.exists():
            return {"deleted": 0, "size": 0}
        
        deleted = 0
        size = 0
        for file_path in temp_path.iterdir():
            if file_path.is_file():
                size += file_path.stat().st_size
                file_path.unlink()
                deleted += 1
        
        return {"deleted": deleted, "size": size}
    except Exception as e:
        return {"error": str(e)}

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not AdminSystem.is_admin(user_id):
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرفين فقط!")
        return
    
    all_channels = AdminSystem.get_all_channels()
    forced_channel = Config.FORCED_CHANNEL
    
    channels_list = ""
    if forced_channel:
        channels_list += f"• @{forced_channel} ✅ (ثابتة)\n"
    
    extra_channels = AdminSystem.load_channels()
    for ch in extra_channels:
        channels_list += f"• @{ch}\n"
    
    if not channels_list:
        channels_list = "لا توجد قنوات"
    
    stats = get_system_stats()
    if "error" not in stats:
        temp_info = f"📁 ملفات مؤقتة: {stats['temp_files']} ({format_size(stats['temp_size'])})\n"
        disk_info = f"💾 التخزين: {format_size(stats['disk_used'])} / {format_size(stats['disk_total'])} ({stats['disk_percent']:.1f}%)\n"
        session_info = f"👥 جلسات نشطة: {stats['active_sessions']}\n"
    else:
        temp_info = "⚠️ لا يمكن جلب الإحصائيات\n"
        disk_info = ""
        session_info = ""
    
    message = (
        "👑 **لوحة تحكم المشرف**\n\n"
        f"📢 **قنوات الاشتراك الإجباري:**\n{channels_list}\n"
        f"🔒 القناة الثابتة: @{forced_channel if forced_channel else 'لا توجد'}\n\n"
        "📊 **إحصائيات سريعة:**\n"
        f"{session_info}{temp_info}{disk_info}\n"
        "🔧 **الأوامر المتاحة:**"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("🗑️ تنظيف الملفات", callback_data="admin_clean")],
        [InlineKeyboardButton("➕ إضافة قناة", callback_data="admin_add_channel")],
        [InlineKeyboardButton("➖ حذف قناة", callback_data="admin_remove_channel")],
        [InlineKeyboardButton("📋 عرض القنوات", callback_data="admin_list_channels")],
        [InlineKeyboardButton("❌ إغلاق", callback_data="admin_close")]
    ])
    
    await update.message.reply_text(message, reply_markup=keyboard, parse_mode="Markdown")

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if not AdminSystem.is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح!")
        return
    
    action = query.data
    
    if action == "admin_close":
        await query.edit_message_text("✅ تم الإغلاق")
        return ConversationHandler.END
    
    elif action == "admin_list_channels":
        all_channels = AdminSystem.get_all_channels()
        forced_channel = Config.FORCED_CHANNEL
        
        text = "📋 **قائمة القنوات:**\n\n"
        if forced_channel:
            text += f"✅ @{forced_channel} (ثابتة)\n"
        
        extra = AdminSystem.load_channels()
        for ch in extra:
            text += f"• @{ch}\n"
        
        if not all_channels:
            text = "📭 لا توجد قنوات مسجلة"
        
        await query.edit_message_text(text, parse_mode="Markdown")
        return
    
    elif action == "admin_add_channel":
        context.user_data['admin_action'] = 'add_channel'
        
        await query.edit_message_text(
            "📝 **إضافة قناة جديدة**\n\n"
            "أرسل معرف القناة بالصيغة التالية:\n"
            "مثال: `@bexo50`\n\n"
            "📌 ملاحظة: القناة الثابتة لا يمكن حذفها\n\n"
            "لإلغاء العملية أرسل /cancel",
            parse_mode="Markdown"
        )
        return ADD_CHANNEL
    
    elif action == "admin_remove_channel":
        extra_channels = AdminSystem.load_channels()
        forced_channel = Config.FORCED_CHANNEL
        
        if not extra_channels:
            await query.edit_message_text("📭 لا توجد قنوات إضافية لحذفها!")
            return
        
        keyboard = []
        for channel in extra_channels:
            keyboard.append([InlineKeyboardButton(
                f"❌ حذف @{channel}",
                callback_data=f"remove_{channel}"
            )])
        keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")])
        
        await query.edit_message_text(
            "🗑️ **اختر القناة لحذفها:**\n\n"
            f"🔒 القناة الثابتة @{forced_channel} لا يمكن حذفها",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    elif action.startswith("remove_"):
        channel = action.replace("remove_", "")
        
        if channel == Config.FORCED_CHANNEL:
            await query.edit_message_text(f"❌ لا يمكن حذف القناة الثابتة @{channel}!")
            return
        
        extra_channels = AdminSystem.load_channels()
        if channel in extra_channels:
            extra_channels.remove(channel)
            AdminSystem.save_channels(extra_channels)
            await query.edit_message_text(f"✅ تم حذف القناة @{channel}!")
        else:
            await query.edit_message_text("❌ القناة غير موجودة!")
        return
    
    elif action == "admin_back":
        await admin_panel(update, context)
        return
    
    elif action == "admin_stats":
        stats = get_system_stats()
        if "error" in stats:
            await query.edit_message_text(f"❌ خطأ: {stats['error']}")
            return
        
        text = (
            "📊 **إحصائيات النظام**\n\n"
            f"🕐 الوقت: {stats['timestamp']}\n\n"
            "💾 **التخزين:**\n"
            f"• الإجمالي: {format_size(stats['disk_total'])}\n"
            f"• المستخدم: {format_size(stats['disk_used'])}\n"
            f"• المتاح: {format_size(stats['disk_free'])}\n"
            f"• النسبة: {stats['disk_percent']:.1f}%\n\n"
            "📁 **الملفات المؤقتة:**\n"
            f"• العدد: {stats['temp_files']}\n"
            f"• الحجم: {format_size(stats['temp_size'])}\n\n"
            f"👥 **الجلسات النشطة:** {stats['active_sessions']}"
        )
        
        await query.edit_message_text(text, parse_mode="Markdown")
        return
    
    elif action == "admin_clean":
        result = clean_temp_files()
        if "error" in result:
            await query.edit_message_text(f"❌ خطأ: {result['error']}")
            return
        
        await query.edit_message_text(
            f"🗑️ **تم تنظيف الملفات المؤقتة!**\n\n"
            f"📁 عدد الملفات المحذوفة: {result['deleted']}\n"
            f"💾 الحجم المحذوف: {format_size(result['size'])}"
        )
        return

async def add_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not AdminSystem.is_admin(user_id):
        await update.message.reply_text("❌ غير مصرح!")
        return ConversationHandler.END
    
    channel_input = update.message.text.strip()
    
    if channel_input == "/cancel":
        await update.message.reply_text("✅ تم إلغاء العملية")
        return ConversationHandler.END
    
    channel = channel_input.replace("@", "").strip()
    
    if not channel:
        await update.message.reply_text(
            "❌ معرف القناة غير صالح!\n"
            "أرسل معرف القناة بالصيغة: `@username`",
            parse_mode="Markdown"
        )
        return ADD_CHANNEL
    
    if channel == Config.FORCED_CHANNEL:
        await update.message.reply_text(f"⚠️ القناة @{channel} هي القناة الثابتة!")
        return ADD_CHANNEL
    
    try:
        chat = await context.bot.get_chat(f"@{channel}")
        
        try:
            bot_member = await context.bot.get_chat_member(
                chat_id=f"@{channel}",
                user_id=context.bot.id
            )
            
            if bot_member.status not in ["administrator", "creator"]:
                await update.message.reply_text(
                    f"⚠️ البوت ليس مشرفاً في القناة @{channel}!"
                )
                return ADD_CHANNEL
                
        except Exception as e:
            await update.message.reply_text(
                f"⚠️ لا يمكن التحقق من صلاحيات البوت في القناة @{channel}!"
            )
            return ADD_CHANNEL
        
        extra_channels = AdminSystem.load_channels()
        if channel in extra_channels:
            await update.message.reply_text(f"⚠️ القناة @{channel} موجودة بالفعل!")
        else:
            extra_channels.append(channel)
            AdminSystem.save_channels(extra_channels)
            await update.message.reply_text(
                f"✅ تم إضافة القناة @{channel} بنجاح!"
            )
        
        await admin_panel(update, context)
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"خطأ في إضافة القناة: {e}")
        await update.message.reply_text(
            f"❌ حدث خطأ: {str(e)[:200]}"
        )
        return ADD_CHANNEL

from keyboards import MAIN_MENU
