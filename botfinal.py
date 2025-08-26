# finals_manager_bot.py
import os
import json
import logging
from typing import Dict, Any
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatAction
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    ConversationHandler, CallbackQueryHandler, filters
)

# ====== الإعدادات (يمكن تخصيصها عبر متغيرات البيئة) ======
BOT_TOKEN = os.getenv("BOT_TOKEN", "8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "6005239475"))   # غيّر إلى رقم الأدمن لديك
CHANNEL_DEST = os.getenv("CHANNEL_DEST", "@RAGEBACKESPORT")     # أو ID القناة إذا كان لديك
LOGO_PATH = os.getenv("LOGO_PATH", "logo.jpg")
DATA_FILE = os.getenv("DATA_FILE", "tournament_data.json")
MAX_TEAMS = int(os.getenv("MAX_TEAMS", "25"))

# ====== تسجيل اللوق ======
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ====== حالات المحادثة ======
(PROOF, CLAN, TAG, COUNTRY) = range(4)

# ====== نصوص واجهة ======
WELCOME_CAPTION = (
    "🔥 *مرحبًا في RAGEBACK ESPORT — Finals Manager* 🔥\n\n"
    "هذا البوت مُخصّص لعمليات التسجيل للفاينلات والحلبات.\n"
    "اضغط *القوانين* لعرض شروط الاشتراك، ثم *التسجيل* للبدء."
)

RULES_TEXT = (
    "📜 *قوانين دخول الفاينلات (مختصرة):*\n\n"
    "1️⃣ الحد الأدنى لمستوى الحساب: *50*.\n"
    "2️⃣ الاحترام واجب — لا سب أو شتائم.\n"
    "3️⃣ الحد الأدنى لحجم الفريق: *3 لاعبين*.\n"
    "4️⃣ يجب دفع رسوم التسجيل (رصيد عبر مشغل محلي) لإثبات الاشتراك.\n"
    "5️⃣ كل فاينل يقبل حتى *25 فريقًا* فقط، ثم يغلق التسجيل.\n\n"
    "اضغط رجوع للعودة."
)

HELP_TEXT = (
    "/start - بدء التفاعل\n"
    "/rules - عرض القوانين\n"
    "/register - بدء التسجيل للفاينل\n"
    "/status - حالة التسجيل وعدد الفرق\n"
    "/my_slot - عرض موقع فريقك (إن نُشِرت بياناتك)\n"
)

# ====== أزرار واجهة ======
def kb_start():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 القوانين", callback_data="show_rules")],
        [InlineKeyboardButton("📝 التسجيل", callback_data="start_register")],
        [InlineKeyboardButton("📢 القناة", url=f"https://t.me/{CHANNEL_DEST.lstrip('@')}")]
    ])

def admin_action_buttons(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ قبول", callback_data=f"admin:accept:{user_id}"),
         InlineKeyboardButton("❌ رفض", callback_data=f"admin:reject:{user_id}")]
    ])

def open_close_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("فتح التسجيل", callback_data="admin:open")],
        [InlineKeyboardButton("إغلاق التسجيل", callback_data="admin:close")],
        [InlineKeyboardButton("نشر اللستة", callback_data="admin:publish")]
    ])

# ====== إدارة البيانات على القرص (JSON) ======
def ensure_data_file():
    if not os.path.exists(DATA_FILE):
        data = {
            "open": False,
            "entries": [],   # list of dicts {user_id, username, clan, tag, country, slot}
            "pending": {}    # user_id -> {proof_text, proof_type}
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def load_data() -> Dict[str, Any]:
    ensure_data_file()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: Dict[str, Any]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ====== مساعد: بناء لستة الفرق كنص ======
def build_entries_text(entries: list) -> str:
    if not entries:
        return "لا توجد فرق مسجلة بعد."
    lines = []
    for e in entries:
        slot = e.get("slot")
        clan = e.get("clan")
        tag = e.get("tag")
        country = e.get("country")
        username = e.get("username") or e.get("user_id")
        lines.append(f"{slot}. {clan} | {tag} | {country} — @{username}")
    return "📋 *قائمة الفرق المسجلة:*\n\n" + "\n".join(lines)

# ====== أوامر أساسية ======
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.message:
        if os.path.exists(LOGO_PATH):
            with open(LOGO_PATH, "rb") as photo:
                await update.message.reply_photo(photo=photo, caption=WELCOME_CAPTION, parse_mode="Markdown", reply_markup=kb_start())
        else:
            await update.message.reply_text(WELCOME_CAPTION, parse_mode="Markdown", reply_markup=kb_start())

async def rules_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(RULES_TEXT, parse_mode="Markdown")

async def show_rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES_TEXT, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

# ====== تسجيل المستخدم: إرسال إثبات الرصيد إلى الأدمن ======
async def register_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = load_data()
    if not data.get("open", False):
        await q.message.reply_text("⚠️ التسجيل مغلق حاليًا. انتظر فتح التسجيل من الإدارة.")
        return
    await q.message.reply_text(
        "🔔 *خطوة إثبات الدفع*\n\n"
        "أرسل صورة إثبات الدفع أو أرسل نص يوضح عملية التحويل (مثلاً: تم تحويل 5000 إلى رقم الخط ...)\n"
        "بعد الإرسال سيصلك رد من الإدارة بالموافقة أو الرفض.", parse_mode="Markdown"
    )
    return PROOF

async def register_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data.get("open", False):
        await update.message.reply_text("⚠️ التسجيل مغلق الآن، انتظر فتح التسجيل.")
        return
    await update.message.reply_text(
        "🔔 *خطوة إثبات الدفع*\n\n"
        "أرسل صورة إثبات الدفع أو أرسل نص يوضح عملية التحويل (مثلاً: تم تحويل ...).", parse_mode="Markdown"
    )
    return PROOF

# استقبال الإثبات (نص أو صورة)
async def proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    if not data.get("open", False):
        await update.message.reply_text("⚠️ التسجيل مغلق، لا يمكن إرسال إثبات الآن.")
        return ConversationHandler.END

    # احصل على نص الإثبات أو رابط الصورة
    proof_text = None
    proof_type = "text"
    if update.message.photo:
        # خزن file_id كإثبات (الأدمن سيشاهده عبر البوت)
        photo = update.message.photo[-1]
        file_id = photo.file_id
        proof_text = f"<photo:{file_id}>"
        proof_type = "photo"
    elif update.message.document:
        doc = update.message.document
        proof_text = f"<doc:{doc.file_id}>"
        proof_type = "doc"
    else:
        proof_text = update.message.text or ""
        proof_type = "text"

    # سجّل كـ pending
    data["pending"][str(user.id)] = {"proof": proof_text, "type": proof_type, "username": user.username or user.id}
    save_data(data)

    # أبلغ المستخدم
    await update.message.reply_text("✅ تم استلام إثبات الدفع. جاري إرسال الطلب للإدارة للمراجعة...")

    # أرسل للأدمن رسالة مع أزرار قبول/رفض
    admin_msg = f"📥 *طلب تسجيل جديد*\n\nمن: @{user.username or user.id}\nUserID: `{user.id}`\n\nإثبات الدفع ({proof_type}):"
    if proof_type == "text":
        admin_msg += f"\n`{proof_text}`"
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown", reply_markup=admin_action_buttons(user.id))
    elif proof_type == "photo":
        # أرسل الصورة للأدمن مع نفس النص
        # proof_text is like "<photo:FILE_ID>"
        file_id = proof_text.split(":", 1)[1].rstrip(">")
        await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=file_id, caption=admin_msg, parse_mode="Markdown", reply_markup=admin_action_buttons(user.id))
    elif proof_type == "doc":
        file_id = proof_text.split(":", 1)[1].rstrip(">")
        await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=file_id, caption=admin_msg, parse_mode="Markdown", reply_markup=admin_action_buttons(user.id))

    return ConversationHandler.END

# ====== قرارات الأدمن على الإثبات (قبول/رفض) ======
async def admin_decision_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    caller = q.from_user
    if caller.id != ADMIN_CHAT_ID:
        await q.message.reply_text("❌ هذا الزر محفوظ للإدارة فقط.")
        return

    data = load_data()
    payload = q.data  # admin:accept:<user_id> or admin:reject:<user_id> or admin:open, admin:close, admin:publish
    parts = payload.split(":")
    action = parts[1] if len(parts) > 1 else None

    # إدارة فتح/إغلاق/نشر
    if action == "open":
        data["open"] = True
        save_data(data)
        await q.message.reply_text("✅ تم فتح التسجيل.")
        return
    if action == "close":
        data["open"] = False
        save_data(data)
        await q.message.reply_text("⛔ تم إغلاق التسجيل.")
        return
    if action == "publish":
        # انشر اللستة النهائية في القناة
        text = build_entries_text(data.get("entries", []))
        await context.bot.send_message(chat_id=CHANNEL_DEST, text=text, parse_mode="Markdown")
        await q.message.reply_text("✅ تم نشر اللستة في القناة.")
        return

    # الإجراءات الخاصة بالمستخدم
    if len(parts) < 3:
        await q.message.reply_text("خطأ: بيانات ناقصة.")
        return
    user_id = parts[2]
    user_pending = data.get("pending", {}).get(str(user_id))
    if not user_pending:
        await q.message.reply_text("⚠️ لا يوجد طلب معلق لهذا المستخدم أو تم التعامل معه مسبقًا.")
        return

    if action == "accept":
        # أرسل رسالة للمستخدم لبدء جمع بيانات الكلان
        try:
            await context.bot.send_message(chat_id=int(user_id),
                                           text="✅ تم قبول إثبات الدفع. الآن أرسل *اسم الكلان* (الاسم الرسمي).",
                                           parse_mode="Markdown")
        except Exception as e:
            logging.exception("Failed sending accept message to user")
            await q.message.reply_text("تم القبول، لكن لم أستطع إرسال رسالة للمستخدم (ربما حظر البوت).")
            # نحتفظ بالـ pending مع العلم أنه مقبول يدوياً؟ لكن سنحذف pending ليمنع تكرار.
        # ضع حالة تقابل بداية عملية جمع البيانات عبر ملف مؤقت 'current_collect' في data
        data.setdefault("collecting", {})[str(user_id)] = {"stage": "clan"}
        # احذف من pending لأننا نقبله
        data["pending"].pop(str(user_id), None)
        save_data(data)
        await q.message.reply_text("✅ تم قبول الطلب وتم إبلاغ المستخدم لبدء إدخال بيانات الكلان.")
        return

    elif action == "reject":
        # راسل المستخدم رفض + سبب عام
        try:
            await context.bot.send_message(chat_id=int(user_id),
                                           text="❌ تم رفض إثبات الدفع أو الطلب. الرجاء التأكد من صحة الإرسال وإعادة المحاولة.",
                                           parse_mode="Markdown")
        except Exception as e:
            logging.exception("Failed sending reject message to user")
        data["pending"].pop(str(user_id), None)
        save_data(data)
        await q.message.reply_text("❌ تم رفض الطلب وحذفه من قائمة الانتظار.")
        return

# ====== جمع اسم الكلان / التاج / الدولة بعد قبول الأدمن ======
async def collect_messages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    coll = data.get("collecting", {}).get(str(user.id))
    if not coll:
        # لا توجد حالة جمع بيانات لهذا المستخدم
        await update.message.reply_text("⚠️ لا يوجد طلب قبول قيد المعالجة. إن لم يبدأ الأدمن بالقبول، استخدم /register.")
        return

    stage = coll.get("stage")
    text = update.message.text.strip()
    if stage == "clan":
        coll["clan"] = text
        coll["stage"] = "tag"
        data["collecting"][str(user.id)] = coll
        save_data(data)
        await update.message.reply_text("✳️ جيد — الآن أرسل *التوحيد (Tag)* الخاص بالكلان (مثال: RBG).", parse_mode="Markdown")
        return
    elif stage == "tag":
        coll["tag"] = text
        coll["stage"] = "country"
        data["collecting"][str(user.id)] = coll
        save_data(data)
        await update.message.reply_text("🏳️ الآن أرسل *علم الدولة* أو اسم الدولة (يمكن إرسال إيموجي العلم 🇮🇶 مثلاً).", parse_mode="Markdown")
        return
    elif stage == "country":
        coll["country"] = text
        # اكتمال: أضف إلى entries إن كان هناك مكان
        entries = data.get("entries", [])
        if len(entries) >= MAX_TEAMS:
            await update.message.reply_text("⚠️ آسف، العدد المكتمل (25 فريق) لذا لا يمكن إضافة فريقك الآن.")
            # نحذف حالة الجمع
            data["collecting"].pop(str(user.id), None)
            save_data(data)
            return

        slot = len(entries) + 1
        entry = {
            "user_id": user.id,
            "username": user.username or user.first_name,
            "clan": coll.get("clan"),
            "tag": coll.get("tag"),
            "country": coll.get("country"),
            "slot": slot
        }
        entries.append(entry)
        data["entries"] = entries
        # حذف حالة الجمع
        data["collecting"].pop(str(user.id), None)
        save_data(data)

        # أرسل تأكيد للمستخدم مع موقعه في اللستة
        await update.message.reply_text(f"✅ تم تسجيل فريقك! موقعك في اللستة: *{slot}*.\nسوف تُرسل لك اللستة الكاملة الآن.", parse_mode="Markdown")

        # أرسل اللستة لجميع المسجلين لإعلامهم بمواقعهم
        list_text = build_entries_text(entries)
        for e in entries:
            try:
                await context.bot.send_message(chat_id=e["user_id"], text=list_text, parse_mode="Markdown")
            except Exception:
                logging.exception(f"Failed to notify user {e['user_id']} about list update")

        # إذا اكمل العدد: أغلق التسجيل وانشر اللستة في القناة
        if len(entries) >= MAX_TEAMS:
            data["open"] = False
            save_data(data)
            final_text = "*✅ الاكتفاء: تم إغلاق التسجيل — اللستة النهائية* \n\n" + build_entries_text(entries)
            # أرسل للقناة
            try:
                await context.bot.send_message(chat_id=CHANNEL_DEST, text=final_text, parse_mode="Markdown")
            except Exception:
                logging.exception("Failed to publish final list to channel")
            # بلّغ الادمن
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text="✅ العدد اكتمل. تم نشر اللستة النهائية في القناة.")
            except Exception:
                logging.exception("Failed to notify admin about completion")
        return

# ====== أوامر حالة ونطاق ======
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    open_state = data.get("open", False)
    entries = data.get("entries", [])
    msg = f"📊 حالة التسجيل: {'مفتوح' if open_state else 'مغلق'}\nعدد الفرق المسجلة: {len(entries)} / {MAX_TEAMS}"
    await update.message.reply_text(msg)

async def my_slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    for e in data.get("entries", []):
        if int(e.get("user_id")) == user.id:
            await update.message.reply_text(f"📍 موقع فريقك: {e.get('slot')} — {e.get('clan')} | {e.get('tag')} | {e.get('country')}")
            return
    await update.message.reply_text("ℹ️ لم يتم العثور على فريق مرتبط بحسابك في هذه اللستة.")

# ====== أوامر إدارية يدوية (من الأدمن فقط) ======
async def admin_panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("هذا الأمر للأدمن فقط.")
        return
    await update.message.reply_text("لوحة إدارة الفاينل:", reply_markup=open_close_buttons())

# ====== تسجيل الهاندلرات ======
def main():
    ensure_data_file()
    app = Application.builder().token(BOT_TOKEN).build()

    # أوامر عادية
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("rules", show_rules_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("register", register_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("my_slot", my_slot_cmd))
    app.add_handler(CommandHandler("admin_panel", admin_panel_cmd))

    # callbacks للأزرار (عرض القوانين - بدء التسجيل)
    app.add_handler(CallbackQueryHandler(rules_cb, pattern="^show_rules$"))
    app.add_handler(CallbackQueryHandler(register_start_cb, pattern="^start_register$"))

    # callback للأزرار الإدارية (قبول/رفض/فتح/إغلاق/نشر)
    app.add_handler(CallbackQueryHandler(admin_decision_cb, pattern="^admin:"))

    # Conversation: proof -> handled by proof_received (MessageHandler)
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(register_start_cb, pattern="^start_register$"), CommandHandler("register", register_cmd)],
        states={
            PROOF: [MessageHandler((filters.PHOTO | filters.Document.ALL | filters.TEXT) & ~filters.COMMAND, proof_received)],
            # جمع بيانات يتم عبر handler عام يتفحص حالة 'collecting' في ملف JSON
        },
        fallbacks=[],
        allow_reentry=True
    )
    app.add_handler(conv)

    # العام: أي رسالة نصية قد تكون جزءًا من جمع الكلان/tag/country بعد قبول الأدمن
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_messages_handler))
    # صور/مستندات أثناء مرحلة الجمع لن تكون مستخدمة — يمكن توسيع لاحقًا

    print("Finals Manager Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
