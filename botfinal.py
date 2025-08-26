# botfinal_complete.py
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
BOT_TOKEN = os.getenv("BOT_TOKEN", "8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "6005239475"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@RAGEBACKESPORT")
LOGO_PATH = os.getenv("LOGO_PATH", "logo.jpg")
MAX_TEAMS = int(os.getenv("MAX_TEAMS", "25"))

STICKER_WELCOME = os.getenv("STICKER_WELCOME", "")
STICKER_ADMIN = os.getenv("STICKER_ADMIN", "")

DATA_FILE = os.getenv("DATA_FILE", "bot_data.json")

teams: List[Dict[str, Any]] = []
pending_payments: Dict[str, Dict[str, Any]] = {}
collecting: Dict[str, Dict[str, Any]] = {}
is_open: bool = False

PROOF = 0
SEEN_CALLBACK_IDS = deque(maxlen=1000)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
WELCOME_PLAYER = (
    "🔥 *أهلًا بيك بـ RAGEBACK ESPORT — Finals Manager* 🔥\n\n"
    "هنا تكمّل تسجيل فريقك للفاينلات بطريقة سهلة وسريعة:\n"
    "1) اطّلع على القوانين\n"
    "2) سجل فريقك وأرسل نوع الرصيد مع الرقم الخاص به\n"
    "مثال:\n🟢 زين\n1234567890\n"
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
    "• دفع رسوم التسجيل (رصيد محلي: 🟢 زين / 🔵 أثير / 🟡 آسيا سيل)\n"
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
        value = p.get("value", "?")
        lines.append(f"{idx}) @{uname} — UserID: `{uid}` — نوع الرصيد: *{p.get('type','?')}* — الرقم: `{value}`")
        idx += 1
    return "📥 *الطلبات المعلقة:*\n\n" + "\n".join(lines)

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
    t = (txt or "").strip().lower().replace(" ", "")
    zain = {"زين", "zain", "zaincash"}
    athe = {"أثير", "اثير", "atheir", "athe"}
    asia = {"آسيا سيل", "آسياسيل", "asiacell", "asia"}
    if t in zain:
        return "🟢 زين"
    if t in athe:
        return "🔵 أثير"
    if t in asia:
        return "🟡 آسيا سيل"
    return ""

def is_emoji_flag(txt: str) -> bool:
    return all('\U0001F1E6' <= c <= '\U0001F1FF' for c in txt if c.strip())

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
        "أرسل الآن نوع الرصيد مع الرقم الخاص به (مثال):\n🟢 زين\n1234567890",
        parse_mode="Markdown"
    )
    return PROOF

async def register_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_open
    if not is_open:
        await update.message.reply_text("⚠️ التسجيل مغلق الآن.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔔 *أرسل نوع الرصيد مع الرقم الآن* (مثال: 🟢 زين / 🔵 أثير / 🟡 آسيا سيل)\nالسطر الثاني الرقم الخاص بالبطاقة.",
        parse_mode="Markdown"
    )
    return PROOF

# ==============================
async def proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pending_payments
    user = update.effective_user
    if not is_open:
        await update.message.reply_text("⚠️ التسجيل مغلق الآن.")
        return ConversationHandler.END

    lines = (update.message.text or "").strip().splitlines()
    if len(lines) < 2:
        await update.message.reply_text(
            "⚠️ الرجاء إرسال الرصيد بشكل صحيح: السطر الأول نوع الرصيد، السطر الثاني الرقم.\nمثال:\n🟢 زين\n1234567890"
        )
        return PROOF

    wallet = normalize_wallet(lines[0])
    value = lines[1].strip()
    if not wallet or not value.isdigit():
        await update.message.reply_text(
            "⚠️ الرجاء إرسال الرصيد بشكل صحيح: نوع الرصيد ثم الرقم (أرقام فقط)."
        )
        return PROOF

    pending_payments[str(user.id)] = {
        "proof": wallet,
        "type": wallet,
        "value": value,
        "username": user.username or user.first_name
    }
    save_all()

    await update.message.reply_text("✅ تم استلام نوع الرصيد والرقم. بانتظار مراجعة الإدارة.")

    admin_msg = (
        f"📥 *طلب تسجيل جديد*\n\n"
        f"من: @{user.username or user.first_name}\n"
        f"UserID: `{user.id}`\n\n"
        f"نوع الرصيد: *{wallet}*\n"
        f"الرقم: `{value}`"
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
# تابع باقي الكود كما في الكود السابق: admin_callback، collect_handler، status_cmd، my_slot_cmd، rules_cmd، admin_panel_cmd
# استمر بنفس الأسلوب مع التحقق من emoji العلم فقط عند استلام الدولة
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

    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(player_register_cb, pattern="^player:register$"),
            CommandHandler("register", register_cmd)
        ],
        states={PROOF: [MessageHandler(filters.TEXT & ~filters.COMMAND, proof_received)]},
        fallbacks=[],
        allow_reentry=True
    )
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(player_rules_cb, pattern="^player:rules$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_handler))

    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()