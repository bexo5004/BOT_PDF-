import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """إعدادات البوت الرئيسية"""
    
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMINS = list(map(int, os.getenv("ADMINS", "").split(","))) if os.getenv("ADMINS") else []
    
    FORCED_CHANNEL = "bexo50"
    FORCED_CHANNELS = []
    
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 50 ميجابايت
    TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
    MAX_SESSION_TIME = 600
    CLEANUP_INTERVAL = 1800
    MAX_FILE_AGE = 3600
    MAX_FILES_PER_SESSION = 50
    
    # الصيغ المدعومة
    SUPPORTED_EXTENSIONS = {
        '.pdf', '.doc', '.docx', '.docm',
        '.xls', '.xlsx', '.xlsm', '.xlsb', '.csv',
        '.ppt', '.pptx', '.pptm', '.ppsx', '.pps',
        '.txt', '.rtf', '.md', '.markdown',
        '.odt', '.ods', '.odp',
        '.html', '.htm', '.xml', '.json',
        '.epub', '.mobi', '.fb2', '.tex',
        '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.gif',
        '.zip', '.rar', '.7z', '.gz', '.tar',
    }
    
    @classmethod
    def ensure_dirs(cls):
        os.makedirs(cls.TEMP_DIR, exist_ok=True)
