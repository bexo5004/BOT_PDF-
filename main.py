import os
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
from config import Config
from utils import (
    logger, set_user_busy, is_user_busy, clean_old_files,
    validate_page_range, format_size, sanitize_filename,
    safe_remove, ensure_extension, get_file_extension,
    is_supported_file, get_file_type_arabic
)
from file_engine import FileEngine
from keyboards import MAIN_MENU, ACTION_MENU, CANCEL_BTN, ADMIN_MENU
from admin import AdminSystem, admin_panel, admin_callback_handler, add_channel_handler, ADD_CHANNEL
from subscription import check_subscription, check_subscription_callback, SubscriptionSystem
from pypdf import PdfReader

Config.ensure_dirs()

@dataclass
class Session:
    files: List[str] = field(default_factory=list)
    action: Optional[str] = None
    val1: Optional[str] = None
    custom_name: Optional[str] = None
    expecting_name: bool = False
    expecting_data: bool = False
    last_active: float = field(default_factory=time.time)
    text_title: Optional[str] = None

user_sessions: Dict[int, Session] = {}
SELECT_ACTION, WAIT_FILE, WAIT_DATA, WAIT_NAME = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_subscription(update, context):
        return SELECT_ACTION
    user_sessions[uid] = Session()
    
    welcome = """👋 **مرحباً بك في بوت المستندات!**
    
📁 **الميزات المتاحة:**
• 📎 دمج PDF
• 🖼️ صور لـ PDF
• 📸 استخراج صور
• 🔢 ترقيم الصفحات
• ✂️ تقسيم
• 🗑️ حذف صفحات
• 📉 ضغط
• 🔒 حماية
• 🔓 إزالة الحماية
• 📝 نص إلى PDF

اختر الأداة من القائمة 🚀"""
    
    await update.message.reply_text(welcome, parse_mode="Markdown", reply_markup=MAIN_MENU)
    
    if AdminSystem.is_admin(uid):
        await update.message.reply_text("👑 مرحباً أيها المشرف!", reply_markup=ADMIN_MENU)
    return SELECT_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    action_text = update.message.text
    
    if action_text == "📝 نص إلى PDF":
        return await handle_text_to_pdf(update, context)
    
    if action_text == "👑 لوحة التحكم":
        if not AdminSystem.is_admin(uid):
            await update.message.reply_text("❌ غير مصرح!", reply_markup=MAIN_MENU)
            return SELECT_ACTION
        await admin_panel(update, context)
        return SELECT_ACTION
    
    if not await check_subscription(update, context):
        return SELECT_ACTION
    
    if is_user_busy(uid):
        await update.message.reply_text("⏳ عملية جارية...", reply_markup=MAIN_MENU)
        return SELECT_ACTION
    
    session = user_sessions.get(uid)
    if not session:
        session = Session()
        user_sessions[uid] = session
    
    session.action = action_text
    session.last_active = time.time()
    
    prompts = {
        "📎 دمج PDF": "📤 أرسل الملفات للدمج",
        "🖼️ صور لـ PDF": "📤 أرسل الصور للتحويل إلى PDF",
        "📸 استخراج صور": "📤 أرسل ملف PDF لاستخراج الصور منه",
        "🔢 ترقيم الصفحات": "📤 أرسل ملف PDF لإضافة أرقام الصفحات",
        "✂️ تقسيم": "📤 أرسل ملف PDF ثم أدخل نطاق الصفحات",
        "🗑️ حذف صفحات": "📤 أرسل ملف PDF ثم أدخل الصفحات للحذف",
        "📉 ضغط": "📤 أرسل ملف PDF لضغطه",
        "🔒 حماية": "📤 أرسل ملف PDF ثم أدخل كلمة المرور",
        "🔓 إزالة الحماية": "📤 أرسل ملف PDF لإزالة الحماية"
    }
    
    await update.message.reply_text(
        prompts.get(action_text, "📤 أرسل الملف المطلوب"),
        reply_markup=ACTION_MENU
    )
    return WAIT_FILE

async def handle_text_to_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج تحويل النص إلى PDF مع عنوان مخصص"""
    uid = update.effective_user.id
    
    if not await check_subscription(update, context):
        return SELECT_ACTION
    
    session = user_sessions.get(uid)
    if not session:
        session = Session()
        user_sessions[uid] = session
    
    session.action = "📝 نص إلى PDF"
    session.last_active = time.time()
    session.expecting_name = True
    
    await update.message.reply_text(
        "📝 **تحويل النص إلى PDF**\n\n"
        "📌 **الخطوة 1:** أرسل **عنوان** المستند\n"
        "📌 **الخطوة 2:** سأطلب منك إرسال النص\n\n"
        "💡 مثال: `تقرير اجتماع` أو `ملخص مشروع`\n\n"
        "📤 أرسل العنوان الآن:",
        reply_markup=CANCEL_BTN,
        parse_mode="Markdown"
    )
    return WAIT_NAME

async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if not await check_subscription(update, context):
        return SELECT_ACTION
    
    session = user_sessions.get(uid)
    if not session:
        return await start(update, context)
    session.last_active = time.time()
    
    photo = update.message.photo[-1]
    
    try:
        file_obj = await context.bot.get_file(photo.file_id)
        filename = f"photo_{os.urandom(4).hex()}.jpg"
        file_path = Path(Config.TEMP_DIR) / f"f_{uid}_{len(session.files)}_{filename}"
        await file_obj.download_to_drive(str(file_path))
        session.files.append(str(file_path))
        
        await update.message.reply_text(
            f"✅ **تم استلام الصورة!**\n"
            f"📁 الملف: `{filename}`\n"
            f"📌 العدد: {len(session.files)}/{Config.MAX_FILES_PER_SESSION}",
            reply_markup=ACTION_MENU,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"خطأ: {e}")
        await update.message.reply_text("❌ حدث خطأ")
    
    return WAIT_FILE

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = user_sessions.get(uid)
    if not session:
        return await start(update, context)
    
    if update.message.text == "❌ إلغاء":
        for file_path in session.files:
            safe_remove(file_path)
        user_sessions.pop(uid, None)
        await update.message.reply_text("✅ تم الإلغاء", reply_markup=MAIN_MENU)
        return SELECT_ACTION
    
    name = update.message.text.strip()
    
    if session.action == "📝 نص إلى PDF":
        if name and len(name) > 0:
            session.text_title = name
            session.expecting_name = False
            
            await update.message.reply_text(
                f"✅ **تم حفظ العنوان:** `{name}`\n\n"
                "📤 **الخطوة 2:** أرسل النص الذي تريد تحويله.\n"
                "📌 يمكنك كتابة النص مباشرة أو إرسال ملف `.txt`",
                reply_markup=ACTION_MENU,
                parse_mode="Markdown"
            )
            return WAIT_FILE
        else:
            await update.message.reply_text(
                "❌ **عنوان فارغ!**\n\n"
                "📤 أرسل عنواناً صالحاً للمستند:",
                reply_markup=CANCEL_BTN,
                parse_mode="Markdown"
            )
            return WAIT_NAME
    
    session.custom_name = None if name.lower() == "تخطي" else ensure_extension(name)
    session.expecting_name = False
    return await process_work(update, context, session)

async def receive_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if not await check_subscription(update, context):
        return SELECT_ACTION
    
    session = user_sessions.get(uid)
    if not session:
        return await start(update, context)
    session.last_active = time.time()

    if update.message.text and session.action == "📝 نص إلى PDF":
        text = update.message.text
        if text and len(text) > 3:
            try:
                title = session.text_title or "نص"
                pdf_path = FileEngine.text_to_pdf(text, title)
                
                with open(pdf_path, 'rb') as f:
                    await update.message.reply_document(
                        f,
                        filename=Path(pdf_path).name,
                        caption=(
                            f"✅ **تم تحويل النص إلى PDF بنجاح!**\n"
                            f"📄 **العنوان:** `{title}`\n"
                            f"🔹 **حقوق البوت:** @BEXO50"
                        ),
                        parse_mode="Markdown"
                    )
                safe_remove(pdf_path)
                
                for file_path in session.files:
                    safe_remove(file_path)
                user_sessions.pop(uid, None)
                return SELECT_ACTION
                
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ: {str(e)[:200]}")
                return WAIT_FILE
        else:
            await update.message.reply_text("❌ النص قصير جداً (يجب أن يكون أكثر من 3 أحرف)")
            return WAIT_FILE

    if update.message.text:
        text = update.message.text
        
        if text == "❌ إلغاء":
            for file_path in session.files:
                safe_remove(file_path)
            user_sessions.pop(uid, None)
            await update.message.reply_text("✅ تم الإلغاء", reply_markup=MAIN_MENU)
            return SELECT_ACTION
        
        if text == "✅ إنهاء العملية":
            if not session.files:
                await update.message.reply_text("⚠️ لم ترسل أي ملفات!", reply_markup=ACTION_MENU)
                return WAIT_FILE
            
            data_actions = ["✂️ تقسيم", "🗑️ حذف صفحات", "🔒 حماية"]
            if session.action in data_actions:
                prompts = {
                    "✂️ تقسيم": "📝 أدخل نطاق الصفحات:",
                    "🗑️ حذف صفحات": "📝 أدخل الصفحات للحذف:",
                    "🔒 حماية": "📝 أدخل كلمة المرور:"
                }
                await update.message.reply_text(prompts[session.action], reply_markup=CANCEL_BTN)
                session.expecting_data = True
                return WAIT_DATA
            
            await update.message.reply_text("📝 أرسل اسم الملف:", reply_markup=CANCEL_BTN)
            session.expecting_name = True
            return WAIT_NAME
        
        if session.expecting_data:
            return await receive_data(update, context)

    if update.message.document:
        document = update.message.document
        filename = document.file_name or "file"
        
        if document.file_size > Config.MAX_FILE_SIZE:
            await update.message.reply_text(f"❌ حجم الملف كبير! الحد {format_size(Config.MAX_FILE_SIZE)}")
            return WAIT_FILE
        
        if len(session.files) >= Config.MAX_FILES_PER_SESSION:
            await update.message.reply_text(f"❌ الحد الأقصى {Config.MAX_FILES_PER_SESSION} ملفات!")
            return WAIT_FILE
        
        try:
            file_obj = await context.bot.get_file(document.file_id)
            ext = get_file_extension(filename)
            file_path = Path(Config.TEMP_DIR) / f"f_{uid}_{len(session.files)}_{os.urandom(4).hex()}{ext}"
            await file_obj.download_to_drive(str(file_path))
            session.files.append(str(file_path))
            
            await update.message.reply_text(
                f"✅ **تم الاستلام!**\n"
                f"📁 الملف: `{Path(filename).name}`\n"
                f"📌 العدد: {len(session.files)}/{Config.MAX_FILES_PER_SESSION}",
                reply_markup=ACTION_MENU,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"خطأ: {e}")
            await update.message.reply_text("❌ حدث خطأ في تحميل الملف")
    
    return WAIT_FILE

async def receive_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = user_sessions.get(uid)
    if not session:
        return await start(update, context)
    
    if update.message.text == "❌ إلغاء":
        for file_path in session.files:
            safe_remove(file_path)
        user_sessions.pop(uid, None)
        await update.message.reply_text("✅ تم الإلغاء", reply_markup=MAIN_MENU)
        return SELECT_ACTION
    
    session.val1 = update.message.text.strip()
    session.expecting_data = False
    
    await update.message.reply_text("📝 أرسل اسم الملف:", reply_markup=CANCEL_BTN)
    session.expecting_name = True
    return WAIT_NAME

async def process_work(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    uid = update.effective_user.id
    set_user_busy(uid, True)
    
    try:
        action = session.action
        result_path = None
        extra_info = ""
        result_is_bytes = False
        result_data = None
        result_filename = None
        
        default_names = {
            "📎 دمج PDF": "ملفات_مدمجة.pdf",
            "🖼️ صور لـ PDF": "صور_محولة.pdf",
            "📸 استخراج صور": "صور_مستخرجة.zip",
            "🔢 ترقيم الصفحات": "ملف_مرقم.pdf",
            "📉 ضغط": "ملف_مضغوط.pdf",
            "🔒 حماية": "ملف_محمي.pdf",
            "✂️ تقسيم": "ملف_مقسم.pdf",
            "🗑️ حذف صفحات": "ملف_معدل.pdf",
            "🔓 إزالة الحماية": "ملف_غير_محمي.pdf"
        }
        
        final_name = session.custom_name or default_names.get(action, "ملف.pdf")
        
        await update.message.reply_text("⏳ جاري المعالجة...")
        
        if action == "📎 دمج PDF":
            result_path = FileEngine.merge_documents(session.files)
            
        elif action == "🖼️ صور لـ PDF":
            result_path = FileEngine.images_to_pdf(session.files)
            
        elif action == "📸 استخراج صور":
            if len(session.files) != 1:
                await update.message.reply_text("❌ يجب إرسال ملف واحد")
                return SELECT_ACTION
            result_data, result_filename = FileEngine.extract_images_from_pdf(session.files[0])
            result_is_bytes = True
            
        elif action == "🔢 ترقيم الصفحات":
            if len(session.files) != 1:
                await update.message.reply_text("❌ يجب إرسال ملف واحد")
                return SELECT_ACTION
            result_path = FileEngine.add_page_numbers(session.files[0])
            
        elif action == "📉 ضغط":
            if len(session.files) != 1:
                await update.message.reply_text("❌ يجب إرسال ملف واحد")
                return SELECT_ACTION
            result_path, before_size, after_size = FileEngine.compress_pdf(session.files[0])
            if before_size != after_size:
                reduction = (1 - after_size / before_size) * 100
                extra_info = f"\n📊 {format_size(before_size)} → {format_size(after_size)} (تخفيض {reduction:.1f}%)"
                
        elif action == "🔒 حماية":
            if len(session.files) != 1:
                await update.message.reply_text("❌ يجب إرسال ملف واحد")
                return SELECT_ACTION
            password = session.val1 or "1234"
            result_path = FileEngine.encrypt_pdf(session.files[0], password)
            extra_info = f"\n🔑 كلمة المرور: `{password}`"
            
        elif action == "✂️ تقسيم":
            if len(session.files) != 1:
                await update.message.reply_text("❌ يجب إرسال ملف واحد")
                return SELECT_ACTION
            result_path = FileEngine.split_pdf(session.files[0], session.val1 or "1")
            
        elif action == "🗑️ حذف صفحات":
            if len(session.files) != 1:
                await update.message.reply_text("❌ يجب إرسال ملف واحد")
                return SELECT_ACTION
            pdf_path = session.files[0]
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)
            page_nums = validate_page_range(session.val1 or "1", total_pages)
            result_path = FileEngine.delete_pages(pdf_path, page_nums)
            
        elif action == "🔓 إزالة الحماية":
            if len(session.files) != 1:
                await update.message.reply_text("❌ يجب إرسال ملف واحد")
                return SELECT_ACTION
            result_path = FileEngine.remove_password(session.files[0])
            extra_info = "\n🔓 تم إزالة الحماية"
        
        if result_is_bytes and result_data:
            await update.message.reply_document(
                result_data,
                filename=result_filename or final_name,
                caption=f"✅ تمت العملية{extra_info}",
                reply_markup=MAIN_MENU
            )
        elif result_path and os.path.exists(result_path):
            with open(result_path, "rb") as file:
                await update.message.reply_document(
                    file,
                    filename=final_name,
                    caption=f"✅ تمت العملية{extra_info}",
                    reply_markup=MAIN_MENU
                )
            safe_remove(result_path)
        else:
            await update.message.reply_text("❌ حدث خطأ", reply_markup=MAIN_MENU)
            
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
        await update.message.reply_text(f"❌ خطأ: {str(e)[:200]}", reply_markup=MAIN_MENU)
        
    finally:
        set_user_busy(uid, False)
        for file_path in session.files:
            safe_remove(file_path)
        user_sessions.pop(uid, None)
    
    return SELECT_ACTION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in user_sessions:
        session = user_sessions[uid]
        for file_path in session.files:
            safe_remove(file_path)
        user_sessions.pop(uid, None)
    await update.message.reply_text("✅ تم الإلغاء", reply_markup=MAIN_MENU)
    return SELECT_ACTION

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not AdminSystem.is_admin(uid):
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرفين فقط!", reply_markup=MAIN_MENU)
        return SELECT_ACTION
    await admin_panel(update, context)
    return SELECT_ACTION

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"خطأ: {context.error}")

async def cleanup_task(context: ContextTypes.DEFAULT_TYPE):
    clean_old_files()
    now = time.time()
    for uid, session in list(user_sessions.items()):
        if now - session.last_active > Config.MAX_SESSION_TIME:
            for file_path in session.files:
                safe_remove(file_path)
            user_sessions.pop(uid, None)

def main():
    if not Config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN غير موجود")
        return
    
    Config.FORCED_CHANNELS = AdminSystem.load_channels()
    
    app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
    
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="check_subscription"))
    app.add_handler(CommandHandler("admin", admin_command))
    
    add_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: ADD_CHANNEL, pattern="admin_add_channel")],
        states={ADD_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_handler)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True
    )
    app.add_handler(add_channel_conv)
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("cancel", cancel)],
        states={
            SELECT_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            WAIT_FILE: [
                MessageHandler(filters.PHOTO & ~filters.COMMAND, receive_photo),
                MessageHandler(filters.Document.ALL & ~filters.COMMAND, receive_files),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_files)
            ],
            WAIT_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_data)],
            WAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)]
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("cancel", cancel)],
        per_user=True
    )
    
    app.add_handler(conv)
    app.add_error_handler(global_error_handler)
    app.job_queue.run_repeating(cleanup_task, interval=Config.CLEANUP_INTERVAL, first=10)
    
    logger.info("🚀 البوت يعمل!")
    logger.info("📝 دعم تحويل النص إلى PDF مع عنوان مخصص")
    logger.info("🔹 حقوق البوت: @BEXO50")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
