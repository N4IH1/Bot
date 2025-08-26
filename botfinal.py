# botfinal.py
import os
import logging
from typing import Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ==============================
# الإعدادات (اضبط القيم أو ضعها في متغيرات البيئة)
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "6005239475"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@RAGEBACKESPORT")  # استخدم @اسم_القناة أو ID رقمي
LOGO_PATH = os.getenv("LOGO_PATH", "logo.jpg")
MAX_TEAMS = int(os.getenv("MAX_TEAMS", "25"))

# بيانات التشغيل (ذاكرة) — يمكن تحويلها لاحقًا إلى ملف JSON إذا رغبت
teams = []  # قائمة الفرق النهائية: كل عنصر dict{"user_id","username","clan","tag","country","slot"}
pending_payments: Dict[str, Dict[str, Any]] = {}  # user_id -> {proof, type, username}
collecting: Dict[str, Dict[str, Any]] = {}  # user_id -> {stage, clan, tag, country}

# حالات الحوارات
PROOF, CLAN, TAG, COUNTRY = range(4)

# تسجيل لوغ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======== أزرار وواجهات ========
def kb_start():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 القوانين", callback_data="rules")],
        [InlineKeyboardButton("📝 التسجيل", callback_data="register")],
        [InlineKeyboardButton("🔗 قناة الفاينل", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")]
    ])

def admin_action_buttons(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ قبول", callback_data=f"admin:accept:{user_id}"),
         InlineKeyboardButton("❌ رفض", callback_data=f"admin:reject:{user_id}")]
    ])

def admin_panel_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("فتح التسجيل", callback_data="admin:open")],
        [InlineKeyboardButton("إغلاق التسجيل", callback_data="admin:close")],
        [InlineKeyboardButton("نشر اللستة الآن", callback_data="admin:publish")]
    ])

# ======== نصوص ========
WELCOME_CAPTION = (
    "🔥 *مرحبًا بك في RAGEBACK ESPORT — Finals Manager* 🔥\n\n"
    "هذا البوت مُخصّص لإدارة تسجيلات الفاينلات: إثبات الدفع، قبول الأدمن، تجميع بيانات الكلان، وترتيب الفرق.\n\n"
    "اضغط على القوانين أولًا ثم ابدأ التسجيل."
)

RULES_TEXT = (
    "📜 *قوانين الفاينلات (مختصرة):*\n\n"
    "• الحد الأدنى لمستوى الحساب: *50*\n"
    "• الاحترام واجب — لا سب أو شتم\n"
    "• الحد الأدنى لحجم الفريق: *3 لاعبين*\n"
    "• يجب دفع رسوم التسجيل (رصيد عبر مشغل محلي)\n"
    "• كل فاينل يقبل حتى *%d* فريقاً\n\n" % MAX_TEAMS
)

# ======== أوامر أساسية ========
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ترحيب + لوغو + أزرار
    if update.message:
        if os.path.exists(LOGO_PATH):
            try:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
            except Exception:
                pass
            with open(LOGO_PATH, "rb") as f:
                await update.message.reply_photo(photo=InputFile(f),
                                                caption=WELCOME_CAPTION,
                                                parse_mode="Markdown",
                                                reply_markup=kb_start())
        else:
            await update.message.reply_text(WELCOME_CAPTION, parse_mode="Markdown", reply_markup=kb_start())

async def rules_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(RULES_TEXT, parse_mode="Markdown")

async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES_TEXT, parse_mode="Markdown")

# ======== تسجيل واثبات الدفع ========
# قبل البدء: تحتاج أن يقوم الأدمن بفتح التسجيل عبر /admin_panel -> "فتح التسجيل" أو زر
is_open = False  # متغير للفتح/الإغلاق (يمكن تحسينه لاحقاً)

async def register_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    global is_open
    if not is_open:
        await q.message.reply_text("⚠️ التسجيل مغلق الآن. انتظر فتح التسجيل من الإدارة.")
        return ConversationHandler.END
    await q.message.reply_text(
        "🔔 *خطوة إثبات الدفع*\n\n"
        "أرسل صورة إثبات الدفع أو اكتب تفاصيل التحويل (مثال: تم تحويل X إلى رقم الخط ...)\n\n"
        "بعد الإرسال سيقوم الأدمن بالمراجعة والموافقة أو الرفض.",
        parse_mode="Markdown"
    )
    return PROOF

async def register_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_open
    if not is_open:
        await update.message.reply_text("⚠️ التسجيل مغلق الآن.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔔 *أرسل إثبات الدفع الآن* (صورة أو نص).",
        parse_mode="Markdown"
    )
    return PROOF

async def proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_open:
        await update.message.reply_text("⚠️ التسجيل مغلق الآن.")
        return ConversationHandler.END

    proof_type = "text"
    proof_payload = ""
    if update.message.photo:
        photo = update.message.photo[-1]
        proof_payload = f"photo:{photo.file_id}"
        proof_type = "photo"
    elif update.message.document:
        doc = update.message.document
        proof_payload = f"doc:{doc.file_id}"
        proof_type = "doc"
    else:
        proof_payload = update.message.text or ""
        proof_type = "text"

    pending_payments[str(user.id)] = {"proof": proof_payload, "type": proof_type, "username": user.username or user.first_name}
    await update.message.reply_text("✅ تم استلام إثبات الدفع. سيتم إرساله للإدارة للمراجعة...")

    # أرسل للأدمن مع أزرار الموافقة/الرفض
    admin_msg = f"📥 طلب تسجيل جديد\n\nمن: @{user.username or user.first_name}\nUserID: `{user.id}`\n\nإثبات ({proof_type}):"
    try:
        if proof_type == "text":
            admin_msg += f"\n`{proof_payload}`"
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown", reply_markup=admin_action_buttons(user.id))
        elif proof_type == "photo":
            file_id = proof_payload.split(":",1)[1]
            await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=file_id, caption=admin_msg, parse_mode="Markdown", reply_markup=admin_action_buttons(user.id))
        elif proof_type == "doc":
            file_id = proof_payload.split(":",1)[1]
            await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=file_id, caption=admin_msg, parse_mode="Markdown", reply_markup=admin_action_buttons(user.id))
    except Exception as e:
        logger.exception("Failed to notify admin about payment")

    return ConversationHandler.END

# ======== استجابة الأدمن (قبول/رفض/فتح/اغلاق/نشر) ========
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    caller = q.from_user

    # فقط الأدمن يمكنه الضغط على أزرار الإدارة
    if caller.id != ADMIN_CHAT_ID:
        await q.message.reply_text("❌ هذا الزر محجوز للإدارة فقط.")
        return

    data = q.data  # شكل: admin:accept:<user_id>  أو admin:reject:<user_id> أو admin:open ...
    parts = data.split(":")
    # admin:open  - admin:close - admin:publish - admin:accept:<id> - admin:reject:<id>
    if len(parts) >= 2:
        action = parts[1]
    else:
        await q.message.reply_text("خطأ في بيانات الزر.")
        return

    global is_open
    if action == "open":
        is_open = True
        await q.message.reply_text("✅ تم فتح التسجيل.")
        return
    if action == "close":
        is_open = False
        await q.message.reply_text("⛔ تم إغلاق التسجيل.")
        return
    if action == "publish":
        # نشر القائمة للقناة
        text = build_list_text()
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
            await q.message.reply_text("✅ تم نشر اللستة في القناة.")
        except Exception:
            logger.exception("Failed to publish list to channel")
            await q.message.reply_text("خطأ عند نشر اللستة.")
        return

    # قبول أو رفض مستخدم محدد
    if action in ("accept", "reject") and len(parts) == 3:
        target_id = parts[2]
        pending = pending_payments.get(str(target_id))
        if not pending:
            await q.message.reply_text("⚠️ لا يوجد إثبات دفع معلق لهذا المستخدم.")
            return

        if action == "reject":
            # أبلغ المستخدم بالرفض
            try:
                await context.bot.send_message(chat_id=int(target_id),
                                               text="❌ تم رفض إثبات الدفع أو الطلب. يرجى التأكد وإعادة المحاولة.")
            except Exception:
                logger.exception("Failed to send reject message to user")
            pending_payments.pop(str(target_id), None)
            await q.message.reply_text("❌ تم رفض الطلب وحذفه.")
            return

        # action == "accept"
        # أبلغ المستخدم ليبدأ بإرسال بيانات الكلان
        try:
            await context.bot.send_message(chat_id=int(target_id),
                                           text="✅ تم قبول إثبات الدفع. الآن أرسل اسم الكلان (الاسم الرسمي).")
        except Exception:
            logger.exception("Failed to send accept message to user")
            # حتى لو فشل إرسال الرسالة، نتابع بتسجيل حالة الجمع
        # انقل من pending إلى collecting
        collecting[str(target_id)] = {"stage": "clan"}
        pending_payments.pop(str(target_id), None)
        await q.message.reply_text("✅ تم قبول الطلب وتم إشعار المستخدم لبدء إدخال بيانات الكلان.")
        return

    await q.message.reply_text("حدث خطأ غير متوقع في تنفيذ الإجراء.")

# ======== جمع بيانات الكلان بعد قبول الأدمن ========
async def collect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in collecting:
        # رسالة عادية أو رسالة غير متوقعة
        return

    stage = collecting[uid].get("stage")
    text = (update.message.text or "").strip()

    if stage == "clan":
        collecting[uid]["clan"] = text
        collecting[uid]["stage"] = "tag"
        await update.message.reply_text("✳️ جيد — الآن أرسل *التوحيد (Tag)* الخاص بالكلان (مثال: RBG).", parse_mode="Markdown")
        return
    if stage == "tag":
        collecting[uid]["tag"] = text
        collecting[uid]["stage"] = "country"
        await update.message.reply_text("🏳️ الآن أرسل *علم الدولة* أو اسم الدولة (يمكن إيموجي 🇮🇶 مثلا).", parse_mode="Markdown")
        return
    if stage == "country":
        collecting[uid]["country"] = text
        # أكمل التسجيل: أضف إلى القائمة إذا مكان متاح
        if len(teams) >= MAX_TEAMS:
            await update.message.reply_text("⚠️ آسف، العدد المكتمل لذا لا يمكن إضافة فريقك الآن.")
            collecting.pop(uid, None)
            return
        slot = len(teams) + 1
        entry = {
            "user_id": int(uid),
            "username": user.username or user.first_name,
            "clan": collecting[uid].get("clan"),
            "tag": collecting[uid].get("tag"),
            "country": collecting[uid].get("country"),
            "slot": slot
        }
        teams.append(entry)
        collecting.pop(uid, None)
        await update.message.reply_text(f"✅ تم تسجيل فريقك! موقعك في اللستة: *{slot}*.", parse_mode="Markdown")

        # أرسل اللستة المحدثة لكل المسجلين ليعرفوا مواقعهم
        list_text = build_list_text()
        for e in teams:
            try:
                await context.bot.send_message(chat_id=e["user_id"], text=list_text, parse_mode="Markdown")
            except Exception:
                logger.exception(f"Failed to notify user {e['user_id']} about updated list")

        # إن اكتمال العدد: أغلق و انشر في القناة وبلغ الأدمن
        if len(teams) >= MAX_TEAMS:
            is_open = False
            try:
                final_text = "*✅ الاكتفاء: تم إغلاق التسجيل — اللستة النهائية* \n\n" + build_list_text()
                await context.bot.send_message(chat_id=CHANNEL_ID, text=final_text, parse_mode="Markdown")
            except Exception:
                logger.exception("Failed to publish final list to channel")
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text="✅ العدد اكتمل. تم نشر اللستة النهائية في القناة.")
            except Exception:
                logger.exception("Failed to notify admin about completion")
        return

# ======== أدوات ========
def build_list_text() -> str:
    if not teams:
        return "لا توجد فرق مسجلة بعد."
    lines = []
    for e in teams:
        lines.append(f"{e['slot']}. {e['clan']} | {e['tag']} | {e['country']} — @{e['username']}")
    return "📋 *قائمة الفرق المسجلة:*\n\n" + "\n".join(lines)

# ======== أوامر حالة ========
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 الحالة: {'مفتوح' if is_open else 'مغلق'}\nعدد الفرق: {len(teams)} / {MAX_TEAMS}")

async def my_slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    for e in teams:
        if e["user_id"] == user.id:
            await update.message.reply_text(f"📍 موقع فريقك: {e['slot']} — {e['clan']} | {e['tag']} | {e['country']}")
            return
    await update.message.reply_text("ℹ️ لم تُسجّل في اللستة الحالية.")

async def admin_panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("هذا الأمر مخصّص للأدمن فقط.")
        return
    await update.message.reply_text("لوحة تحكم الأدمن:", reply_markup=admin_panel_buttons())

# ======== تسجيل الهاندلرات وتشغيل البوت ========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("register", register_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("my_slot", my_slot_cmd))
    app.add_handler(CommandHandler("admin_panel", admin_panel_cmd))

    # callback buttons
    app.add_handler(CallbackQueryHandler(rules_cb, pattern="^rules$"))
    app.add_handler(CallbackQueryHandler(register_start_cb, pattern="^register$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))

    # Conversation for payment proof
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(register_start_cb, pattern="^register$"), CommandHandler("register", register_cmd)],
        states={
            PROOF: [MessageHandler((filters.PHOTO | filters.Document.ALL | filters.TEXT) & ~filters.COMMAND, proof_received)],
        },
        fallbacks=[],
        allow_reentry=True
    )
    app.add_handler(conv)

    # general message handler for collecting clan/tag/country
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()