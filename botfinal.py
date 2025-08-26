# botfinal.py
import os
import json
import logging
from typing import Dict, Any, List

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
BOT_TOKEN = os.getenv("BOT_TOKEN", "8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")  # فضلاً عيّن التوكن بمتغير بيئة
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "6005239475"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@RAGEBACKESPORT")  # استخدم @اسم_القناة أو ID رقمي
LOGO_PATH = os.getenv("LOGO_PATH", "logo.jpg")
MAX_TEAMS = int(os.getenv("MAX_TEAMS", "25"))

# ستيكرات اختيارية (خليها فاضية إذا ما عندك)
STICKER_WELCOME = os.getenv("STICKER_WELCOME", "")  # ستيكر للترحيب بالمستخدمين
STICKER_ADMIN = os.getenv("STICKER_ADMIN", "")      # ستيكر خاص بالأدمن

DATA_FILE = os.getenv("DATA_FILE", "bot_data.json")

# بيانات التشغيل (ذاكرة + تخزين JSON)
teams: List[Dict[str, Any]] = []  # قائمة الفرق النهائية: dict{"user_id","username","clan","tag","country","slot"}
pending_payments: Dict[str, Dict[str, Any]] = {}  # user_id -> {proof, type, username}
collecting: Dict[str, Dict[str, Any]] = {}  # user_id -> {stage, clan, tag, country}
is_open: bool = False  # حالة التسجيل

# حالات الحوارات
PROOF = 0  # نستعمل مرحلة واحدة للإثبات؛ بقية الجمع يُدار برسائل عادية بعدها

# تسجيل لوغ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======== تخزين وتحميل JSON ========
def save_all():
    try:
        data = {
            "teams": teams,
            "pending_payments": pending_payments,
            "collecting": collecting,
            "is_open": is_open
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to save data")

def load_all():
    global teams, pending_payments, collecting, is_open
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        teams = data.get("teams", [])
        pending_payments = data.get("pending_payments", {})
        collecting = data.get("collecting", {})
        is_open = data.get("is_open", False)
    except Exception:
        logger.exception("Failed to load data")

# ======== أزرار وواجهات ========
def kb_player_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 القوانين", callback_data="player:rules")],
        [InlineKeyboardButton("📝 التسجيل", callback_data="player:register")],
        [InlineKeyboardButton("📢 قناة الفاينل", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")]
    ])

def kb_admin_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 فتح التسجيل", callback_data="admin:open"),
         InlineKeyboardButton("🔴 إغلاق التسجيل", callback_data="admin:close")],
        [InlineKeyboardButton("📥 الطلبات المعلقة", callback_data="admin:view_pending")],
        [InlineKeyboardButton("📋 عرض اللستة", callback_data="admin:view_teams")],
        [InlineKeyboardButton("📣 نشر اللستة الآن", callback_data="admin:publish")]
    ])

def admin_action_buttons(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ قبول", callback_data=f"admin:accept:{user_id}"),
         InlineKeyboardButton("❌ رفض", callback_data=f"admin:reject:{user_id}")]
    ])

# ======== نصوص ========
WELCOME_PLAYER = (
    "🔥 *أهلًا بيك بـ RAGEBACK ESPORT — Finals Manager* 🔥\n\n"
    "هنا تكمّل تسجيل فريقك للفاينلات بطريقة سهلة وسريعة:\n"
    "1) اطّلع على القوانين\n"
    "2) سجل فريقك وأرسل إثبات الدفع\n"
    "3) انتظر موافقة الإدارة ثم أكمل بيانات الكلان\n\n"
    "خلّك محترف 👑… وخلّي فريقك يتصدّر اللستة!\n"
)

WELCOME_ADMIN = (
    "🛠️ *لوحة تحكم الأدمن — RAGEBACK ESPORT*\n\n"
    "من هنا تكدر تفتح/تغلق التسجيل، تراجع طلبات الدفع، وتنشر اللستة.\n"
    "اختر الإجراء المطلوب من الأزرار أدناه."
)

RULES_TEXT = lambda: (
    "📜 *قوانين الفاينلات:*\n\n"
    "• الحد الأدنى لمستوى الحساب: *50*\n"
    "• الاحترام واجب — لا سب أو شتم\n"
    "• الحد الأدنى لحجم الفريق: *3 لاعبين*\n"
    "• دفع رسوم التسجيل (رصيد عبر مشغل محلي)\n"
    f"• كل فاينل يقبل حتى *{MAX_TEAMS}* فريقاً\n\n"
    "✅ التزم بالقوانين وتمنّى التوفيق لفريقك!"
)

def build_list_text() -> str:
    if not teams:
        return "لا توجد فرق مسجلة بعد."
    lines = []
    for e in teams:
        uname = f"@{e['username']}" if e.get("username") else f"ID:{e['user_id']}"
        lines.append(f"{e['slot']}. {e['clan']} | {e['tag']} | {e['country']} — {uname}")
    return "📋 *قائمة الفرق المسجلة:*\n\n" + "\n".join(lines)

def build_pending_preview() -> str:
    if not pending_payments:
        return "لا توجد طلبات دفع معلّقة حالياً."
    lines = []
    idx = 1
    for uid, p in pending_payments.items():
        uname = p.get("username") or uid
        lines.append(f"{idx}) @{uname} — UserID: `{uid}` — نوع الإثبات: *{p.get('type','?')}*")
        idx += 1
    return "📥 *الطلبات المعلقة:*\n\n" + "\n".join(lines)

# ======== أدوات إرسال لطيفة ========
async def try_send_sticker(context: ContextTypes.DEFAULT_TYPE, chat_id: int, sticker_id: str):
    if not sticker_id:
        return
    try:
        await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_id)
    except Exception:
        # تجاهل الخطأ إذا الستيكر غير صالح/غير متاح للبوت
        pass

# ======== واجهات بحسب نوع المستخدم ========
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = (user.id == ADMIN_CHAT_ID)

    # لوغو (إن وجد)
    if update.message:
        if os.path.exists(LOGO_PATH):
            try:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
            except Exception:
                pass
            with open(LOGO_PATH, "rb") as f:
                await update.message.reply_photo(
                    photo=InputFile(f),
                    caption=WELCOME_ADMIN if is_admin else WELCOME_PLAYER,
                    parse_mode="Markdown",
                    reply_markup=kb_admin_home() if is_admin else kb_player_home()
                )
        else:
            await update.message.reply_text(
                WELCOME_ADMIN if is_admin else WELCOME_PLAYER,
                parse_mode="Markdown",
                reply_markup=kb_admin_home() if is_admin else kb_player_home()
            )

        # ستيكر ترحيبي
        await try_send_sticker(context, update.effective_chat.id, STICKER_ADMIN if is_admin else STICKER_WELCOME)

# ======== أزرار اللاعب ========
async def player_rules_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(RULES_TEXT(), parse_mode="Markdown")

async def player_register_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    global is_open
    if not is_open:
        await q.message.reply_text("⚠️ التسجيل مغلق الآن. انتظر فتح التسجيل من الإدارة.")
        return ConversationHandler.END
    await q.message.reply_text(
        "🔔 *خطوة إثبات الدفع*\n\n"
        "أرسل الآن **صورة** إثبات الدفع أو **مستند** أو **نص** تفاصيل التحويل.\n"
        "بعد الإرسال رح توصل للأدمن ويوافق/يرفض.",
        parse_mode="Markdown"
    )
    return PROOF

async def register_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_open
    if not is_open:
        await update.message.reply_text("⚠️ التسجيل مغلق الآن.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔔 *أرسل إثبات الدفع الآن* (صورة أو مستند أو نص).",
        parse_mode="Markdown"
    )
    return PROOF

# ======== استقبال إثبات الدفع ========
async def proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pending_payments
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
        proof_payload = (update.message.text or "").strip()
        proof_type = "text"

    pending_payments[str(user.id)] = {
        "proof": proof_payload,
        "type": proof_type,
        "username": user.username or user.first_name
    }
    save_all()

    await update.message.reply_text("✅ تم استلام إثبات الدفع. بانتظار مراجعة الإدارة.")

    # إشعار الأدمن مع أزرار قبول/رفض
    admin_msg = (
        f"📥 *طلب تسجيل جديد*\n\n"
        f"من: @{user.username or user.first_name}\n"
        f"UserID: `{user.id}`\n\n"
        f"إثبات (*{proof_type}*):"
    )
    try:
        if proof_type == "text":
            admin_msg_full = admin_msg + f"\n`{proof_payload}`"
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_msg_full,
                parse_mode="Markdown",
                reply_markup=admin_action_buttons(user.id)
            )
        elif proof_type == "photo":
            file_id = proof_payload.split(":", 1)[1]
            await context.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=file_id,
                caption=admin_msg,
                parse_mode="Markdown",
                reply_markup=admin_action_buttons(user.id)
            )
        elif proof_type == "doc":
            file_id = proof_payload.split(":", 1)[1]
            await context.bot.send_document(
                chat_id=ADMIN_CHAT_ID,
                document=file_id,
                caption=admin_msg,
                parse_mode="Markdown",
                reply_markup=admin_action_buttons(user.id)
            )
    except Exception:
        logger.exception("Failed to notify admin about payment")

    return ConversationHandler.END

# ======== أزرار الأدمن ========
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    caller = q.from_user

    if caller.id != ADMIN_CHAT_ID:
        await q.message.reply_text("❌ هذا الزر محجوز للإدارة فقط.")
        return

    data = q.data  # admin:open / admin:close / admin:publish / admin:view_pending / admin:view_teams / admin:accept:<id> / admin:reject:<id>
    parts = data.split(":")
    action = parts[1] if len(parts) >= 2 else ""

    global is_open, pending_payments

    if action == "open":
        is_open = True
        save_all()
        await q.message.reply_text("🟢 تم فتح التسجيل.")
        return

    if action == "close":
        is_open = False
        save_all()
        await q.message.reply_text("🔴 تم إغلاق التسجيل.")
        return

    if action == "publish":
        text = build_list_text()
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
            await q.message.reply_text("✅ تم نشر اللستة في القناة.")
        except Exception:
            logger.exception("Failed to publish list to channel")
            await q.message.reply_text("⚠️ خطأ عند نشر اللستة.")
        return

    if action == "view_pending":
        text = build_pending_preview()
        # نبني أزرار قبول/رفض لكل طلب (حتى 10 عناصر لتجنب كيبورد ضخم)
        rows = []
        count = 0
        for uid in list(pending_payments.keys()):
            if count >= 10:
                break
            rows.append([
                InlineKeyboardButton(f"✅ قبول {uid}", callback_data=f"admin:accept:{uid}"),
                InlineKeyboardButton(f"❌ رفض {uid}", callback_data=f"admin:reject:{uid}")
            ])
            count += 1
        if not rows:
            rows = [[InlineKeyboardButton("رجوع", callback_data="admin:back_home")]]
        else:
            rows.append([InlineKeyboardButton("🔄 تحديث", callback_data="admin:view_pending"),
                         InlineKeyboardButton("🏠 رجوع", callback_data="admin:back_home")])
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
        return

    if action == "view_teams":
        text = build_list_text()
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 رجوع", callback_data="admin:back_home")]
        ]))
        return

    if action == "back_home":
        await q.message.reply_text("🏠 الرجوع للوحة الأدمن:", reply_markup=kb_admin_home())
        return

    # قبول/رفض مستخدم محدد
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
                                               text="❌ تم رفض إثبات الدفع. يرجى التأكد وإعادة المحاولة.")
            except Exception:
                logger.exception("Failed to send reject message to user")
            pending_payments.pop(str(target_id), None)
            save_all()
            await q.message.reply_text(f"❌ تم رفض طلب UserID: {target_id}.")
            return

        # قبول
        try:
            await context.bot.send_message(chat_id=int(target_id),
                                           text="✅ تم قبول إثبات الدفع. أرسل *اسم الكلان الرسمي* الآن.",
                                           parse_mode="Markdown")
        except Exception:
            logger.exception("Failed to send accept message to user")
        collecting[str(target_id)] = {"stage": "clan"}
        pending_payments.pop(str(target_id), None)
        save_all()
        await q.message.reply_text(f"✅ تم قبول طلب UserID: {target_id}. تم إشعار المستخدم لبدء إدخال بيانات الكلان.")
        return

    await q.message.reply_text("⚠️ إجراء غير معروف.")

# ======== جمع بيانات الكلان بعد قبول الأدمن ========
async def collect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in collecting:
        return  # رسالة عادية لا تخص الجمع

    stage = collecting[uid].get("stage")
    text = (update.message.text or "").strip()

    if stage == "clan":
        if not text:
            await update.message.reply_text("🙁 رجاءً أرسل *اسم الكلان* نصًّا.")
            return
        collecting[uid]["clan"] = text
        collecting[uid]["stage"] = "tag"
        save_all()
        await update.message.reply_text("✳️ تمام! الآن أرسل *التاغ (Tag)* للكلان (مثال: RBG).", parse_mode="Markdown")
        return

    if stage == "tag":
        if not text:
            await update.message.reply_text("🙁 رجاءً أرسل *التاغ* نصًّا.")
            return
        collecting[uid]["tag"] = text
        collecting[uid]["stage"] = "country"
        save_all()
        await update.message.reply_text("🏳️ الآن أرسل *الدولة/العلم* (إيموجي 🇮🇶 أو اسم الدولة).", parse_mode="Markdown")
        return

    if stage == "country":
        if not text:
            await update.message.reply_text("🙁 رجاءً أرسل *الدولة/العلم* نصًّا.")
            return

        collecting[uid]["country"] = text

        # أكمل التسجيل: أضف إلى القائمة إذا مكان متاح
        if len(teams) >= MAX_TEAMS:
            collecting.pop(uid, None)
            save_all()
            await update.message.reply_text("⚠️ آسف، العدد اكتمل وما نكدر نضيف فريقك الآن.")
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
        save_all()

        await update.message.reply_text(
            f"✅ تم تسجيل فريقك! موقعك في اللستة: *{slot}*.\n"
            "🔥 بالتوفيق! لا تنس تتابع القناة للمستجدات.",
            parse_mode="Markdown"
        )

        # أرسل اللستة المحدثة لكل المسجلين ليعرفوا مواقعهم
        list_text = build_list_text()
        for e in teams:
            try:
                await context.bot.send_message(chat_id=e["user_id"], text=list_text, parse_mode="Markdown")
            except Exception:
                logger.exception(f"Failed to notify user {e['user_id']} about updated list")

        # إن اكتمل العدد: أغلق وانشر في القناة وبلغ الأدمن
        if len(teams) >= MAX_TEAMS:
            global is_open
            is_open = False
            save_all()
            try:
                final_text = "*✅ الاكتفاء: تم إغلاق التسجيل — اللستة النهائية*\n\n" + build_list_text()
                await context.bot.send_message(chat_id=CHANNEL_ID, text=final_text, parse_mode="Markdown")
            except Exception:
                logger.exception("Failed to publish final list to channel")
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text="✅ العدد اكتمل. تم نشر اللستة النهائية في القناة.")
            except Exception:
                logger.exception("Failed to notify admin about completion")
        return

# ======== أوامر حالة ========
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 الحالة: {'🟢 مفتوح' if is_open else '🔴 مغلق'}\n"
        f"عدد الفرق: {len(teams)} / {MAX_TEAMS}"
    )

async def my_slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    for e in teams:
        if e["user_id"] == user.id:
            await update.message.reply_text(
                f"📍 موقع فريقك: {e['slot']} — {e['clan']} | {e['tag']} | {e['country']}"
            )
            return
    await update.message.reply_text("ℹ️ لم تُسجّل في اللستة الحالية.")

async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES_TEXT(), parse_mode="Markdown")

async def admin_panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("هذا الأمر مخصّص للأدمن فقط.")
        return
    await update.message.reply_text("لوحة تحكم الأدمن:", reply_markup=kb_admin_home())
    await try_send_sticker(context, update.effective_chat.id, STICKER_ADMIN)

# ======== تسجيل الهاندلرات وتشغيل البوت ========
def main():
    load_all()

    if not BOT_TOKEN:
        raise RuntimeError("فضلاً عيّن BOT_TOKEN كمتغير بيئة قبل التشغيل.")

    app = Application.builder().token(BOT_TOKEN).build()

    # أوامر عامة
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("register", register_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("my_slot", my_slot_cmd))
    app.add_handler(CommandHandler("admin_panel", admin_panel_cmd))

    # أزرار اللاعب
    app.add_handler(CallbackQueryHandler(player_rules_cb, pattern="^player:rules$"))
    app.add_handler(CallbackQueryHandler(player_register_cb, pattern="^player:register$"))

    # أزرار الأدمن
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))

    # Conversation لإثبات الدفع
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(player_register_cb, pattern="^player:register$"),
            CommandHandler("register", register_cmd)
        ],
        states={
            PROOF: [MessageHandler((filters.PHOTO | filters.Document.ALL | filters.TEXT) & ~filters.COMMAND, proof_received)],
        },
        fallbacks=[],
        allow_reentry=True
    )
    app.add_handler(conv)

    # جمع بيانات الكلان/التاغ/الدولة
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()