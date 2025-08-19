import re
import unicodedata
import threading
import time
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler

# Namespace برای جلوگیری از تداخل
profanity_system = {
    "permanent_whitelist": {5710720196, 71071326, 5656222989, 1150627080, 493728826},
    "whitelist_ids": set(),
    "filter_status": True,
    "filter_sensitivity": "medium",
    "base_words": set(),
    "profanity_filter": None,
    "global_locked_chats": set(),  # چت‌های با قفل سراسری
    "reply_filter_enabled": True,  # فیلتر پاسخ روی ریپلای
}

# تنظیمات اولیه
profanity_system["whitelist_ids"] = profanity_system["permanent_whitelist"].copy()

# کلمات پیش‌فرض برای فیلتر
DEFAULT_BAD_WORDS = {
    'کیر', 'کص', 'جون', 'کوص', 'کوبص', 'کصکش', 'کونی', 'جنده', 
    'کون', 'دیوس', 'دیوص', 'جق', 'ننت', 'ننه',
    'حرومزاده', 'حروم', 'تخم', 'بی‌ناموس', 'سیک', 'صیک', 'جاکش', 'کسکش', 'کصو', 'عشقم', 'سو', 'کین', 'قین', 
}
profanity_system["base_words"] = DEFAULT_BAD_WORDS.copy()

# لیست الگوهای پیشرفته
ADVANCED_PATTERNS = [
    r'\bپدر\s*سوخته\b',
    r'\bمادر\s*جنده\b',
    r'\bخواهر\s*جنده\b',
    r'\bنوب\s*سگ\b',
    r'\bبی\s*ناموس\b',
    r'\bحروم\s*زاده\b',
    r'\bخار\s*کسه\b',
    r'\bکون\s*ده\b',
    r'\bکس\s*خل\b',
    r'\bکیر\s*خر\b',
    r'\bنوف\s*سگ\b',
    r'\bکش\s*لیس\b',
    r'\bخواهر\s*کس\b',
    r'\bبرادر\s*کس\b',
    r'\bحروم\s*لقمه\b'
]

# الگوهای ویژه برای حساسیت بالا (بدون فاصله و کاراکتر اضافه)
ADVANCED_PATTERNS_HIGH = [
    r'پدرسوخته', r'مادرجنده', r'خواهرجنده', r'نوبسگ', r'بیناموس',
    r'حرومزاده', r'خارکسه', r'کونده', r'کسخل', r'کیرخر',
    r'نوفسگ', r'کشلیس', r'خواهرکس', r'برادرکس', r'حروملقمه'
]

class UltimateProfanityFilter:
    def __init__(self):
        self.patterns = [re.compile(pattern, re.IGNORECASE) for pattern in ADVANCED_PATTERNS]
        self.advanced_high_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in ADVANCED_PATTERNS_HIGH]
        self.custom_patterns = []
        
        # اضافه کردن پترن‌های پیش‌فرض
        for word in DEFAULT_BAD_WORDS:
            self._add_custom_pattern_unsafe(word)

    def _normalize(self, text):
        try:
            text = unicodedata.normalize('NFKC', text)
            text = re.sub(r'[^\w\sآ-ی]', '', text)
            return text.lower()
        except Exception:
            return text.lower()

    def _aggressive_clean(self, text):
        """پاکسازی کامل متن - حذف همه چیز غیر از حروف فارسی"""
        try:
            cleaned = re.sub(r'[^\u0600-\u06FF]', '', text)
            cleaned = re.sub(r'(.)\1{2,}', r'\1\1', cleaned)
            return cleaned.strip()
        except Exception:
            return text.strip()

    def _medium_clean(self, text):
        """پاکسازی متوسط - حذف نمادها ولی حفظ فاصله‌ها"""
        try:
            cleaned = re.sub(r'[^\u0600-\u06FF\s]', '', text)
            cleaned = re.sub(r'(.)\1{3,}', r'\1\1', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned)
            return cleaned.strip()
        except Exception:
            return text.strip()

    def _reduce_repeats(self, text):
        try:
            return re.sub(r'(.)\1{2,}', r'\1\1', text)
        except Exception:
            return text

    def is_profane(self, text, sensitivity="medium"):
        if not text or len(text.strip()) < 2:
            return False
        try:
            original = text.lower()
            normalized = self._normalize(text)
            reduced = self._reduce_repeats(original)
            medium_clean = self._medium_clean(original)
            aggressive_clean = self._aggressive_clean(original)
            
            texts_to_check = [
                original,
                normalized,
                reduced,
                medium_clean,
                aggressive_clean
            ]

            for pattern in self.patterns:
                for check_text in texts_to_check:
                    if check_text and pattern.search(check_text):
                        return True

            for pattern in self.custom_patterns:
                if aggressive_clean and pattern.search(aggressive_clean):
                    if sensitivity == "high":
                        return True
                    elif sensitivity == "medium":
                        if len(aggressive_clean) <= 30:
                            return True
                    elif sensitivity == "low":
                        if len(aggressive_clean) <= 10 and any(word in aggressive_clean for word in ['کیر', 'کص', 'کونی', 'جنده', 'کون']):
                            return True

            if sensitivity == "high":
                ultra_clean = self._aggressive_clean(text)
                for bad_word in profanity_system["base_words"]:
                    if bad_word in ultra_clean:
                        return True
                for pattern in self.advanced_high_patterns:
                    if pattern.search(ultra_clean):
                        return True
            return False
        except Exception as e:
            return False

    def _add_custom_pattern_unsafe(self, word):
        normalized_word = self._normalize(word)
        cleaned_word = self._aggressive_clean(normalized_word)
        if not cleaned_word:
            return
        try:
            flexible_pattern = ""
            for i, char in enumerate(cleaned_word):
                flexible_pattern += re.escape(char)
                if i < len(cleaned_word) - 1:
                    flexible_pattern += f'(?:{re.escape(char)}{{0,5}}[.\\-_*!@#$%^&()+=\\[\\]{{}}|\\\\/:;"\'<>?~`\\s]{{0,3}})*'
            if cleaned_word:
                last_char = cleaned_word[-1]
                flexible_pattern += f'{re.escape(last_char)}{{0,10}}'
            pattern = re.compile(flexible_pattern, re.IGNORECASE)
            self.custom_patterns.append(pattern)
        except Exception as e:
            pass

    def add_custom_pattern(self, word):
        self._add_custom_pattern_unsafe(word)
        profanity_system["base_words"].add(word)

    def remove_custom_pattern(self, word):
        normalized_word = self._normalize(word)
        cleaned_word = self._aggressive_clean(normalized_word)
        if not cleaned_word:
            return
        try:
            flexible_pattern = ""
            for i, char in enumerate(cleaned_word):
                flexible_pattern += re.escape(char)
                if i < len(cleaned_word) - 1:
                    flexible_pattern += f'(?:{re.escape(char)}{{0,5}}[.\\-_*!@#$%^&()+=\\[\\]{{}}|\\\\/:;"\'<>?~`\\s]{{0,3}})*'
            if cleaned_word:
                last_char = cleaned_word[-1]
                flexible_pattern += f'{re.escape(last_char)}{{0,10}}'
            self.custom_patterns = [p for p in self.custom_patterns if p.pattern != flexible_pattern]
            profanity_system["base_words"].discard(word)
        except Exception as e:
            pass

# ایجاد فیلتر (فقط اگه وجود نداره)
if profanity_system["profanity_filter"] is None:
    profanity_system["profanity_filter"] = UltimateProfanityFilter()

# فیلتر اصلی - ساده و کاربردی
async def ultimate_filter(client, message):
    try:
        # چک‌های اولیه
        if not profanity_system["filter_status"] or not message.from_user:
            return
        if message.from_user.id in profanity_system["whitelist_ids"]:
            return
            
        text = message.text or message.caption or ""
        if not text:
            return
        
        # چک فحش
        is_bad = profanity_system["profanity_filter"].is_profane(text, profanity_system["filter_sensitivity"])
        if not is_bad:
            return
            
        # پیوی: همیشه حذف
        if message.chat.type == "private":
            try:
                await message.delete()
            except:
                pass
            return
                    
        # گروه: فقط اگر ریپلای روی ما باشه یا قفل سراسری باشه
        if message.chat.type in ["group", "supergroup"]:
            # چک ریپلای روی ما
            if (profanity_system["reply_filter_enabled"] and 
                message.reply_to_message and 
                message.reply_to_message.from_user and 
                message.reply_to_message.from_user.is_self):
                try:
                    await message.delete()
                except:
                    pass
                return
                        
            # چک قفل سراسری
            if message.chat.id in profanity_system["global_locked_chats"]:
                try:
                    await message.delete()
                except:
                    pass
                    
    except Exception:
        pass

# دستورات موجود قبلی...
async def set_low_sensitivity(client, message):
    try:
        profanity_system["filter_sensitivity"] = "low"
        await message.edit(
            "✅ حساسیت فیلتر روی **پایین** تنظیم شد. 🎚️ (0-20%)\n\n"
            "🔹 این سطح فقط فحش‌های آشکار و شدید را حذف می‌کند.\n"
            "🔹 پیام‌های طولانی را کمتر محدود می‌کند.\n"
            "🔹 مثال: حذف پیام‌های کوتاه حاوی کلماتی مثل «کیر»، «کونی»"
        )
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def set_medium_sensitivity(client, message):
    try:
        profanity_system["filter_sensitivity"] = "medium"
        await message.edit(
            "✅ حساسیت فیلتر روی **متوسط** تنظیم شد. 🎚️ (40-60%)\n\n"
            "🔹 این سطح فحش‌های رایج و ترکیبی را تشخیص می‌دهد.\n"
            "🔹 پیام‌های متوسط را حذف می‌کند.\n"
            "🔹 مثال: حذف پیام‌های حاوی «کیر تو»، «مادرجنده»"
        )
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def set_high_sensitivity(client, message):
    try:
        profanity_system["filter_sensitivity"] = "high"
        await message.edit(
            "✅ حساسیت فیلتر روی **بالا** تنظیم شد. 🎚️ (80-97%)\n\n"
            "🔹 این سطح به شدت سخت‌گیر است و هرگونه فحش را حذف می‌کند.\n"
            "🔹 حتی با کاراکترهای مخفی و املای غلط.\n"
            "🔹 مثال: حذف پیام‌های حاوی «کـ ـیـر»، «ک.ی.ر»، «م+ادر+ج+نده»"
        )
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def show_sensitivity(client, message):
    try:
        current = profanity_system["filter_sensitivity"]
        level_text = {"low": "پایین (0-20%)", "medium": "متوسط (40-60%)", "high": "بالا (80-97%)"}
        await message.edit(f"🎚️ حساسیت فعلی: **{level_text.get(current, current)}**")
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def add_bad_word(client, message):
    try:
        word = message.text.split(' ', 1)[1].strip()
        if word in profanity_system["base_words"]:
            await message.edit(f"ℹ️ کلمه «{word}» قبلاً در لیست فیلتر است.")
            return
        profanity_system["profanity_filter"].add_custom_pattern(word)
        await message.edit(f"✅ کلمه «{word}» به لیست فیلتر اضافه شد.")
    except Exception as e:
        await message.edit(f"❌ خطا در اضافه کردن کلمه: {e}")

async def remove_bad_word(client, message):
    try:
        word = message.text.split(' ', 2)[2].strip()
        if word in profanity_system["base_words"]:
            profanity_system["profanity_filter"].remove_custom_pattern(word)
            await message.edit(f"✅ کلمه «{word}» از لیست فیلتر حذف شد.")
        else:
            await message.edit(f"ℹ️ کلمه «{word}» در لیست فیلتر نبود.")
    except Exception as e:
        await message.edit(f"❌ خطا در حذف کلمه: {e}")

async def show_bad_words(client, message):
    try:
        words_list = [word for word in profanity_system["base_words"]]
        if not words_list:
            await message.edit("⚠️ لیست فیلتر خالی است.")
            return
        
        text = "📃 کلمات فیلتر شده:\n\n"
        for i, word in enumerate(sorted(words_list), 1):
            text += f"{i}. {word}\n"
        
        text += f"\n🔢 مجموع: {len(words_list)} کلمه"
        await message.edit(text)
    except Exception as e:
        await message.edit(f"❌ خطا در نمایش لیست: {str(e)}")

async def turn_on_filter(client, message):
    try:
        profanity_system["filter_status"] = True
        await message.edit("✅ فیلتر فعال شد.")
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def turn_off_filter(client, message):
    try:
        profanity_system["filter_status"] = False
        await message.edit("🚫 فیلتر غیرفعال شد.")
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def whitelist_add(client, message):
    try:
        if not message.reply_to_message:
            await message.edit("❌ لطفاً روی پیام شخص ریپلای کن.")
            return
        uid = message.reply_to_message.from_user.id
        if uid in profanity_system["whitelist_ids"]:
            await message.edit("ℹ️ این کاربر قبلاً آزاد بود.")
            return
        profanity_system["whitelist_ids"].add(uid)
        await message.edit(f"✅ کاربر `{uid}` از فیلتر معاف شد.")
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def whitelist_add_by_id(client, message):
    try:
        uid = int(message.text.split()[-1])
        if uid in profanity_system["whitelist_ids"]:
            await message.edit(f"ℹ️ کاربر `{uid}` قبلاً آزاد بود.")
            return
        profanity_system["whitelist_ids"].add(uid)
        await message.edit(f"✅ کاربر `{uid}` از فیلتر معاف شد.")
    except ValueError:
        await message.edit("❌ آیدی وارد شده معتبر نیست.")
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def whitelist_remove(client, message):
    try:
        if not message.reply_to_message:
            await message.edit("❌ لطفاً روی پیام کاربر ریپلای کن.")
            return
        uid = message.reply_to_message.from_user.id
        if uid in profanity_system["permanent_whitelist"]:
            await message.edit("⚠️ این کاربر در لیست دائمی آزاد است و قابل حذف نیست.")
            return
        if uid in profanity_system["whitelist_ids"]:
            profanity_system["whitelist_ids"].discard(uid)
            await message.edit(f"🚫 کاربر `{uid}` از لیست آزاد حذف شد.")
        else:
            await message.edit("ℹ️ این کاربر قبلاً آزاد نبود.")
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def whitelist_remove_by_id(client, message):
    try:
        uid = int(message.text.split()[-1])
        if uid in profanity_system["permanent_whitelist"]:
            await message.edit(f"⚠️ کاربر `{uid}` در لیست دائمی آزاد است و قابل حذف نیست.")
            return
        if uid in profanity_system["whitelist_ids"]:
            profanity_system["whitelist_ids"].discard(uid)
            await message.edit(f"🚫 کاربر `{uid}` از لیست آزاد حذف شد.")
        else:
            await message.edit(f"ℹ️ کاربر `{uid}` قبلاً آزاد نبود.")
    except ValueError:
        await message.edit("❌ آیدی وارد شده معتبر نیست.")
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def whitelist_show(client, message):
    try:
        whitelist_copy = profanity_system["whitelist_ids"].copy()
        if not whitelist_copy:
            await message.edit("🔓 لیست آزاد خالی است.")
            return
        text = "🔓 کاربران معاف از فیلتر:\n\n"
        for uid in sorted(whitelist_copy):
            status = "🛡️ دائمی" if uid in profanity_system["permanent_whitelist"] else "✅ موقت"
            text += f"• `{uid}` {status}\n"
        text += f"\n🔢 مجموع: {len(whitelist_copy)} کاربر"
        await message.edit(text)
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

# دستورات جدید برای قفل سراسری
async def global_lock_chat(client, message):
    try:
        parts = message.text.split()
        if len(parts) < 4:
            await message.edit("❌ فرمت: قفل فحش سراسری در @group یا 123456")
            return
            
        chat_identifier = parts[-1]
        
        # تشخیص نوع شناسه
        if chat_identifier.startswith('@'):
            # یوزرنیم چت
            try:
                chat = await client.get_chat(chat_identifier)
                chat_id = chat.id
                chat_title = chat.title or chat_identifier
            except:
                await message.edit(f"❌ چت {chat_identifier} یافت نشد")
                return
        else:
            # ایدی عددی
            try:
                chat_id = int(chat_identifier)
                try:
                    chat = await client.get_chat(chat_id)
                    chat_title = chat.title or f"چت {chat_id}"
                except:
                    chat_title = f"چت {chat_id}"
            except ValueError:
                await message.edit("❌ ایدی چت معتبر نیست")
                return
        
        if chat_id in profanity_system["global_locked_chats"]:
            await message.edit(f"ℹ️ چت **{chat_title}** قبلاً قفل بود")
            return
            
        profanity_system["global_locked_chats"].add(chat_id)
        await message.edit(
            f"🔒 **قفل فحش سراسری فعال شد**\n\n"
            f"📱 **چت:** {chat_title}\n"
            f"🔢 **ایدی:** `{chat_id}`\n"
            f"⚡ **حساسیت:** {profanity_system['filter_sensitivity']}\n\n"
            f"✅ حالا همه فحش‌ها در این چت حذف می‌شوند"
        )
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def global_unlock_chat(client, message):
    try:
        parts = message.text.split()
        if len(parts) < 4:
            await message.edit("❌ فرمت: حذف قفل سراسری @group یا 123456")
            return
            
        chat_identifier = parts[-1]
        
        # تشخیص نوع شناسه
        if chat_identifier.startswith('@'):
            # یوزرنیم چت
            try:
                chat = await client.get_chat(chat_identifier)
                chat_id = chat.id
                chat_title = chat.title or chat_identifier
            except:
                await message.edit(f"❌ چت {chat_identifier} یافت نشد")
                return
        else:
            # ایدی عددی
            try:
                chat_id = int(chat_identifier)
                try:
                    chat = await client.get_chat(chat_id)
                    chat_title = chat.title or f"چت {chat_id}"
                except:
                    chat_title = f"چت {chat_id}"
            except ValueError:
                await message.edit("❌ ایدی چت معتبر نیست")
                return
        
        if chat_id not in profanity_system["global_locked_chats"]:
            await message.edit(f"ℹ️ چت **{chat_title}** قبلاً قفل نبود")
            return
            
        profanity_system["global_locked_chats"].discard(chat_id)
        await message.edit(
            f"🔓 **قفل فحش سراسری حذف شد**\n\n"
            f"📱 **چت:** {chat_title}\n"
            f"🔢 **ایدی:** `{chat_id}`\n\n"
            f"✅ فیلتر سراسری در این چت غیرفعال شد"
        )
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

async def show_global_locks(client, message):
    try:
        if not profanity_system["global_locked_chats"]:
            await message.edit("🔓 هیچ چتی قفل سراسری ندارد")
            return
            
        text = "🔒 **چت‌های قفل سراسری:**\n\n"
        
        for i, chat_id in enumerate(sorted(profanity_system["global_locked_chats"]), 1):
            try:
                chat = await client.get_chat(chat_id)
                chat_title = chat.title or f"چت {chat_id}"
            except:
                chat_title = f"چت حذف شده {chat_id}"
                
            text += f"{i}. **{chat_title}**\n"
            text += f"   └─ ایدی: `{chat_id}`\n\n"
        
        text += f"🔢 **مجموع:** {len(profanity_system['global_locked_chats'])} چت"
        await message.edit(text)
    except Exception as e:
        await message.edit(f"❌ خطا: {e}")

# تابع برای اضافه کردن هندلرها
def setup_profanity_handlers(app):
    """اضافه کردن هندلرهای فیلتر به اپ"""
    try:
        if hasattr(app, '_profanity_handlers_added'):
            return
            
        # فیلتر اصلی
        app.add_handler(MessageHandler(ultimate_filter, ~filters.me & (filters.private | filters.group)), group=11)
        
        # دستورات مدیریت
        app.add_handler(MessageHandler(set_low_sensitivity, filters.me & filters.regex(r"^حساسیت پایین$")), group=11)
        app.add_handler(MessageHandler(set_medium_sensitivity, filters.me & filters.regex(r"^حساسیت متوسط$")), group=11)
        app.add_handler(MessageHandler(set_high_sensitivity, filters.me & filters.regex(r"^حساسیت بالا$")), group=11)
        app.add_handler(MessageHandler(show_sensitivity, filters.me & filters.regex(r"^حساسیت$")), group=11)
        app.add_handler(MessageHandler(add_bad_word, filters.me & filters.regex(r"^فیلترپیوی .+")), group=11)
        app.add_handler(MessageHandler(remove_bad_word, filters.me & filters.regex(r"^حذف فیلترپیوی .+")), group=11)
        app.add_handler(MessageHandler(show_bad_words, filters.me & filters.regex(r"^لیست فیلتر$")), group=11)
        app.add_handler(MessageHandler(turn_on_filter, filters.me & filters.regex(r"^فیلتر روشن$")), group=11)
        app.add_handler(MessageHandler(turn_off_filter, filters.me & filters.regex(r"^فیلتر خاموش$")), group=11)
        app.add_handler(MessageHandler(whitelist_add, filters.me & filters.regex(r"^این آزاده$")), group=11)
        app.add_handler(MessageHandler(whitelist_add_by_id, filters.me & filters.regex(r"^این ازاده \d+$")), group=11)
        app.add_handler(MessageHandler(whitelist_remove, filters.me & filters.regex(r"^حذف آزاد$")), group=11)
        app.add_handler(MessageHandler(whitelist_remove_by_id, filters.me & filters.regex(r"^حذف ازاد \d+$")), group=11)
        app.add_handler(MessageHandler(whitelist_show, filters.me & filters.regex(r"^لیست آزاد$")), group=11)
        
        # دستورات قفل سراسری
        app.add_handler(MessageHandler(global_lock_chat, filters.me & filters.regex(r"^قفل فحش سراسری در .+")), group=11)
        app.add_handler(MessageHandler(global_unlock_chat, filters.me & filters.regex(r"^حذف قفل سراسری .+")), group=11)
        app.add_handler(MessageHandler(show_global_locks, filters.me & filters.regex(r"^لیست قفل سراسری$")), group=11)
        
        app._profanity_handlers_added = True
        print("✅ فیلتر فحش با موفقیت لود شد!")
        
    except Exception as e:
        print(f"❌ خطا در لود فیلتر: {e}")

# اگر app موجود باشه، هندلرها رو اضافه کن
try:
    if 'app' in globals():
        setup_profanity_handlers(app)
except:
    print("⚠️ app یافت نشد - هندلرها بعداً اضافه می‌شوند")
    print("برای فعال‌سازی: setup_profanity_handlers(app) را اجرا کنید")