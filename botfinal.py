# botfinal.py
import os
import json
import logging
from typing import Dict, Any, List
from collections import deque

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
# الإعدادات
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "6005239475"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@RAGEBACKESPORT")
LOGO_PATH = os.getenv("LOGO_PATH", "logo.jpg")
MAX_TEAMS = int(os.getenv("MAX_TEAMS", "25"))

STICKER_WELCOME = os.getenv("STICKER_WELCOME", "")
STICKER_ADMIN = os.getenv("STICKER_ADMIN", "")

DATA_FILE = os.getenv("DATA_FILE", "bot_data.json")

# بيانات
teams: List[Dict[str, Any]] = []
pending_payments: Dict[str, Dict[str, Any]] = {}
collecting: Dict[str, Dict[str, Any]] = {}
is_open: bool = False

# Conversation states
PROOF = 0

# مكافحة نقر/تحديث مكرر
SEEN_CALLBACK_IDS = deque(maxlen=1000)

# لوغ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================
# تخزين/تحميل
# ==============================
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

# ==============================
# واجهات
# ==============================
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

# ==============================
# نصوص
# ==============================
WELCOME_PLAYER = (
    "🔥 *أهلًا بيك بـ RAGEBACK ESPORT — Finals Manager* 🔥\n\n"
    "هنا تكمّل تسجيل فريقك للفاينلات بطريقة سهلة وسريعة:\n"
    "1) اطّلع على القوانين\n"
    "2) سجل فريقك وأرسل نوع الرصيد مع رقم البطاقة (زين / أثير / آسيا سيل)\n"
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
    "• دفع رسوم التسجيل (رصيد محلي: زين / أثير / آسيا سيل)\n"
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
        lines.append(f"{idx}) @{uname} — UserID: `{uid}` — نوع الرصيد: *{p.get('type','?')}*")
        idx += 1
    return "📥 *الطلبات المعلقة:*\n\n" + "\n".join(lines)

# ==============================
# أدوات مساعدة
# ==============================
async def try_send_sticker(context: ContextTypes.DEFAULT_TYPE, chat_id: int, sticker_id: str):
    if not sticker_id:
        return
    try:
        await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_id)
    except Exception:
        pass

def is_duplicate_callback(callback_id: str) -> bool:
    if callback_id in SEEN_CALLBACK_IDS:
        return True
    SEEN_CALLBACK_IDS.append(callback_id)
    return False

def normalize_wallet(txt: str) -> str:
    """يحاول تحويل النص إلى واحدة من: زين / أثير / آسيا سيل"""
    t = (txt or "").strip().lower().replace(" ", "")
    zain = {"زين", "زينكاش", "zain", "zaincash", "zain-cash", "zaincashh"}
    athe = {"أثير", "اثير", "atheir", "athe er", "atheeer", "atheir", "athe"}
    asia = {"آسياسيل", "اسياسيل", "اسياسيل", "اسياسير", "أساسير",
            "آسياسيل", "asiacell", "asia-cell", "asiacel", "asia"}
    if t in zain:
        return "زين"
    if t in athe:
        return "أثير"
    if t in asia:
        return "آسيا سيل"
    return ""

# ==============================
# واجهات بحسب نوع المستخدم
# ==============================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = (user.id == ADMIN_CHAT_ID)

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
        await try_send_sticker(context, update.effective_chat.id, STICKER_ADMIN if is_admin else STICKER_WELCOME)

# ==============================
# Player buttons
# ==============================
async def player_rules_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if is_duplicate_callback(q.id):
        await q.answer()
        return
    await q.answer()
    await q.message.reply_text(RULES_TEXT(), parse_mode="Markdown")

async def player_register_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if is_duplicate_callback(q.id):
        await q.answer()
        return ConversationHandler.END
    await q.answer()
    global is_open
    if not is_open:
        await q.message.reply_text("⚠️ التسجيل مغلق الآن. انتظر فتح التسجيل من الإدارة.")
        return ConversationHandler.END
    await q.message.reply_text(
        "🔔 *خطوة تسجيل الرصيد*\n\n"
        "أرسل نوع الرصيد مع الرقم (مثال: زين 1234567890).\n"
        "بعد الإرسال سيصلك إشعار من الإدارة بالموافقة أو الرفض.",
        parse_mode="Markdown"
    )
    return PROOF

async def register_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_open
    if not is_open:
        await update.message.reply_text("⚠️ التسجيل مغلق الآن.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔔 *أرسل نوع الرصيد مع الرقم الآن* (زين / أثير / آسيا سيل + الرقم).",
        parse_mode="Markdown"
    )
    return PROOF

# ==============================
# استقبال نوع الرصيد
# ==============================
async def proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pending_payments
    user = update.effective_user
    if not is_open:
        await update.message.reply_text("⚠️ التسجيل مغلق الآن.")
        return ConversationHandler.END

    wallet_raw = (update.message.text or "").strip()
    parts = wallet_raw.split(maxsplit=1)
    wallet_type = normalize_wallet(parts[0]) if parts else ""
    wallet_number = parts[1] if len(parts) > 1 else ""

    if not wallet_type or not wallet_number:
        await update.message.reply_text("⚠️ الرجاء إرسال النوع والرقم صحيحين: زين 12345 أو أثير 67890 ...")
        return PROOF

    pending_payments[str(user.id)] = {
        "proof": wallet_raw,
        "type": wallet_type,
        "number": wallet_number,
        "username": user.username or user.first_name
    }
    save_all()

    await update.message.reply_text("✅ تم استلام الرصيد. بانتظار مراجعة الإدارة.")

    admin_msg = (
        f"📥 *طلب تسجيل جديد*\n\n"
        f"من: @{user.username or user.first_name}\n"
        f"UserID: `{user.id}`\n\n"
        f"نوع الرصيد: *{wallet_type}*\n"
        f"رقم البطاقة: `{wallet_number}`"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_msg,
            parse_mode="Markdown",
            reply_markup=admin_action_buttons(user.id)
        )
    except Exception:
        logger.exception("Failed to notify admin about payment")

    return ConversationHandler.END

# ==============================
# Admin buttons & actions
# ==============================
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if is_duplicate_callback(q.id):
        await q.answer()
        return
    await q.answer()
    caller = q.from_user

    if caller.id != ADMIN_CHAT_ID:
        await q.message.reply_text("❌ هذا الزر محجوز للإدارة فقط.")
        return

    data = q.data
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
            rows = [[InlineKeyboardButton("🏠 رجوع", callback_data="admin:back_home")]]
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

    if action in ("accept", "reject") and len(parts) == 3:
        target_id = parts[2]
        pending = pending_payments.get(str(target_id))
        if not pending:
            await q.message.reply_text("⚠️ لا يوجد طلب دفع معلّق لهذا المستخدم.")
            return

        if action == "reject":
            try:
                await context.bot.send_message(chat_id=int(target_id),
                                               text="❌ تم رفض إثبات الدفع. يرجى التأكد وإعادة المحاولة.")
            except Exception:
                logger.exception("Failed to send reject message to user")
            pending_payments.pop(str(target_id), None)
            save_all()
            await q.message.reply_text(f"❌ تم رفض طلب UserID: {target_id}.")
            return

        try:
            await context.bot.send_message(chat_id=int(target_id),
                                           text="✅ تم قبول نوع الرصيد. أرسل *اسم الكلان الرسمي* الآن.",
                                           parse_mode="Markdown")
        except Exception:
            logger.exception("Failed to send accept message to user")
        collecting[str(target_id)] = {"stage": "clan"}
        pending_payments.pop(str(target_id), None)
        save_all()
        await q.message.reply_text(f"✅ تم قبول طلب UserID: {target_id}. تم إشعار المستخدم لبدء إدخال بيانات الكلان.")
        return

    await q.message.reply_text("⚠️ إجراء غير معروف.")

# ==============================
# جمع بيانات الكلان
# ==============================
async def collect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in collecting:
        return

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
        await update.message.reply_text("🏳️ الآن أرسل *العلم* فقط (مثال: 🇮🇶).", parse_mode="Markdown")
        return

    if stage == "country":
        if not text:
            await update.message.reply_text("🙁 رجاءً أرسل *العلم* نصًّا.")
            return

        collecting[uid]["country"] = text

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

        list_text = build_list_text()
        for e in teams:
            try:
                await context.bot.send_message(chat_id=e["user_id"], text=list_text, parse_mode="Markdown")
            except Exception:
                logger.exception(f"Failed to notify user {e['user_id']} about updated list")

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

# ==============================
# أوامر حالة
# ==============================
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

# ==============================
# تشغيل البوت
# ==============================
def main():
    load_all()

    if not BOT_TOKEN:
        raise RuntimeError("8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")

    app = Application.builder().token(BOT_TOKEN).build()

    # أوامر عامة
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("my_slot", my_slot_cmd))
    app.add_handler(CommandHandler("admin_panel", admin_panel_cmd))

    # Conversation لإثبات نوع الرصيد
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(player_register_cb, pattern="^player:register$"),
            CommandHandler("register", register_cmd)
        ],
        states={
            PROOF: [MessageHandler(filters.TEXT & ~filters.COMMAND, proof_received)],
        },
        fallbacks=[],
        allow_reentry=True
    )
    app.add_handler(conv)

    # أزرار اللاعب الأخرى
    app.add_handler(CallbackQueryHandler(player_rules_cb, pattern="^player:rules$"))

    # أزرار الأدمن
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))

    # جمع بيانات الكلان/التاغ/الدولة
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_handler))

    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()