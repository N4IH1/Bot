# botfinal_complete_fixed_full.py
import os
import json
import logging
from typing import Dict, Any, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler, filters, ContextTypes

# ==============================
# إعدادات
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "6005239475"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@RAGEBACKESPORT")
LOGO_PATH = os.getenv("LOGO_PATH", "logo.jpg")
MAX_TEAMS = int(os.getenv("MAX_TEAMS", "25"))

STICKER_WELCOME = os.getenv("STICKER_WELCOME", "")
STICKER_ADMIN = os.getenv("STICKER_ADMIN", "")

DATA_FILE = os.getenv("DATA_FILE", "bot_data.json")

# بيانات البوت
teams: List[Dict[str, Any]] = []
pending_payments: Dict[str, Dict[str, Any]] = {}
collecting: Dict[str, Dict[str, Any]] = {}
is_open: bool = False

# Conversation states
PROOF = 0

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
    "2) سجل فريقك وأرسل نوع الرصيد (زين / آسيا) ثم رقم البطاقة\n"
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
    "• دفع رسوم التسجيل (رصيد محلي: زين / آسيا)\n"
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
        lines.append(f"{idx}) @{uname} — UserID: `{uid}` — نوع الرصيد: *{p.get('type','?')}* — البطاقة: `{p.get('card','?')}`")
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

def normalize_wallet(txt: str) -> str:
    t = (txt or "").strip().lower().replace(" ", "")
    zain = {"زين", "زينكاش", "zain", "zaincash"}
    asia = {"اسيا", "آسياسيل", "asiacell", "asia-cell", "asia"}
    if t in zain:
        return "زين"
    if t in asia:
        return "اسيا"
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
# أزرار اللاعب
# ==============================
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
        return
    await q.message.reply_text(
        "🔔 *خطوة تسجيل الرصيد*\n\n"
        "أرسل الآن نوع الرصيد فقط: *زين* أو *اسيا*.\n"
        "بعد الإرسال سيصلك إشعار من الإدارة بالموافقة أو الرفض.",
        parse_mode="Markdown"
    )
    return PROOF

# ==============================
# استقبال نوع الرصيد + رقم البطاقة
# ==============================
async def proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pending_payments, collecting
    user = update.effective_user
    uid = str(user.id)

    text = (update.message.text or "").strip()
    stage = collecting.get(uid, {}).get("stage")

    if not stage:
        wallet = normalize_wallet(text)
        if not wallet:
            await update.message.reply_text("⚠️ الرجاء إرسال نوع الرصيد الصحيح: زين أو اسيا")
            return PROOF
        collecting[uid] = {"stage": "number", "wallet": wallet}
        await update.message.reply_text(f"✳️ نوع الرصيد مسجل: *{wallet}*\nالآن أرسل رقم البطاقة.", parse_mode="Markdown")
        return PROOF

    elif stage == "number":
        wallet = collecting[uid]["wallet"]
        card_number = text
        pending_payments[uid] = {
            "type": wallet,
            "card": card_number,
            "username": user.username or user.first_name
        }
        collecting.pop(uid, None)
        save_all()

        await update.message.reply_text("✅ تم إرسال طلبك للإدارة. انتظر الموافقة.")

        admin_msg = (
            f"📥 *طلب تسجيل جديد*\n\n"
            f"من: @{user.username or user.first_name}\n"
            f"UserID: `{uid}`\n\n"
            f"نوع الرصيد: *{wallet}*\n"
            f"رقم البطاقة: `{card_number}`"
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_msg,
                parse_mode="Markdown",
                reply_markup=admin_action_buttons(uid)
            )
        except Exception:
            logger.exception("Failed to notify admin about payment")
        return ConversationHandler.END

# ==============================
# أزرار الأدمن + جمع بيانات الكلان بعد قبول الأدمن
# ==============================
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    caller = q.from_user

    if caller.id != ADMIN_CHAT_ID:
        await q.message.reply_text("❌ هذا الزر محجوز للإدارة فقط.")
        return

    data = q.data
    parts = data.split(":")
    action = parts[1] if len(parts) >= 2 else ""

    global is_open, pending_payments

    try:
        if action == "open":
            is_open = True
            save_all()
            await q.edit_message_text("🟢 تم فتح التسجيل.", reply_markup=kb_admin_home())
            return

        if action == "close":
            is_open = False
            save_all()
            await q.edit_message_text("🔴 تم إغلاق التسجيل.", reply_markup=kb_admin_home())
            return

        if action == "publish":
            text = build_list_text()
            try:
                await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
                await q.edit_message_text("✅ تم نشر اللستة في القناة.", reply_markup=kb_admin_home())
            except Exception:
                logger.exception("Failed to publish list to channel")
                await q.edit_message_text("⚠️ خطأ عند نشر اللستة.", reply_markup=kb_admin_home())
            return

        if action == "view_pending":
            text = build_pending_preview()
            rows = []
            for uid in pending_payments.keys():
                rows.append([
                    InlineKeyboardButton(f"✅ قبول {uid}", callback_data=f"admin:accept:{uid}"),
                    InlineKeyboardButton(f"❌ رفض {uid}", callback_data=f"admin:reject:{uid}")
                ])
            if not rows:
                rows = [[InlineKeyboardButton("🏠 رجوع", callback_data="admin:back_home")]]
            else:
                rows.append([InlineKeyboardButton("🔄 تحديث", callback_data="admin:view_pending"),
                             InlineKeyboardButton("🏠 رجوع", callback_data="admin:back_home")])
            await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
            return

        if action == "view_teams":
            text = build_list_text()
            await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 رجوع", callback_data="admin:back_home")]
            ]))
            return

        if action == "back_home":
            await q.edit_message_text("🏠 الرجوع للوحة الأدمن:", reply_markup=kb_admin_home())
            return

        if action in ("accept", "reject") and len(parts) == 3:
            target_id = parts[2]
            pending = pending_payments.get(str(target_id))
            if not pending:
                await q.edit_message_text("⚠️ لا يوجد طلب دفع معلّق لهذا المستخدم.", reply_markup=kb_admin_home())
                return

            if action == "reject":
                try:
                    await context.bot.send_message(chat_id=int(target_id),
                                                   text="❌ تم رفض إثبات الدفع. يرجى التأكد وإعادة المحاولة.")
                except Exception:
                    logger.exception("Failed to send reject message to user")
                pending_payments.pop(str(target_id), None)
                save_all()
                await q.edit_message_text(f"❌ تم رفض طلب UserID: {target_id}.", reply_markup=kb_admin_home())
                return

            try:
                await context.bot.send_message(
                    chat_id=int(target_id),
                    text="✅ تم قبول الرصيد. الآن أرسل *اسم الكلان الرسمي*.",
                    parse_mode="Markdown"
                )
            except Exception:
                logger.exception("Failed to send accept message to user")
            collecting[str(target_id)] = {"stage": "clan"}
            pending_payments.pop(str(target_id), None)
            save_all()
            await q.edit_message_text(f"✅ تم قبول طلب UserID: {target_id}. تم إشعار المستخدم لبدء إدخال بيانات الكلان.", reply_markup=kb_admin_home())
            return

    except Exception:
        logger.exception("Error in admin_callback")
        await q.edit_message_text("⚠️ حدث خطأ أثناء تنفيذ الأمر.", reply_markup=kb_admin_home())
        return

# ==============================
# جمع بيانات الكلان بعد قبول الأدمن
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
        await update.message.reply_text("✳️ تم تسجيل اسم الكلان. الآن أرسل *التاج الرسمي* للفريق.")
        return

    if stage == "tag":
        if not text:
            await update.message.reply_text("🙁 رجاءً أرسل *تاج الفريق* نصًّا.")
            return
        collecting[uid]["tag"] = text
        collecting[uid]["stage"] = "country"
        await update.message.reply_text("✳️ تم تسجيل التاج. الآن أرسل *اسم الدولة* للفريق.")
        return

    if stage == "country":
        if not text:
            await update.message.reply_text("🙁 رجاءً أرسل *اسم الدولة* نصًّا.")
            return
        collecting[uid]["country"] = text

        slot = len(teams) + 1
        new_team = {
            "slot": slot,
            "user_id": uid,
            "username": user.username or user.first_name,
            "clan": collecting[uid]["clan"],
            "tag": collecting[uid]["tag"],
            "country": collecting[uid]["country"]
        }
        teams.append(new_team)
        collecting.pop(uid, None)
        save_all()
        await update.message.reply_text(f"✅ تم تسجيل فريقك بنجاح في اللستة. رقم الفريق: {slot}")
        return

# ==============================
# إعداد التطبيق
# ==============================
def main():
    load_all()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))
    app.add_handler(CallbackQueryHandler(player_rules_cb, pattern="^player:rules$"))
    app.add_handler(CallbackQueryHandler(player_register_cb, pattern="^player:register$"))

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & (~filters.COMMAND), proof_received)],
        states={
            PROOF: [MessageHandler(filters.TEXT & (~filters.COMMAND), proof_received)],
        },
        fallbacks=[]
    )
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), collect_handler))

    app.run_polling()

if __name__ == "__main__":
    main()