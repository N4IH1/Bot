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
# Configuration (غير ضروري إذا استخدمت متغيرات بيئة)
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "6005239475"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@RAGEBACKESPORT")
LOGO_PATH = os.getenv("LOGO_PATH", "logo.jpg")
MAX_TEAMS = int(os.getenv("MAX_TEAMS", "25"))

STICKER_WELCOME = os.getenv("STICKER_WELCOME", "")  # ضع ستيكر id إن رغبت
STICKER_ADMIN = os.getenv("STICKER_ADMIN", "")

DATA_FILE = os.getenv("DATA_FILE", "bot_data.json")

# ==============================
# In-memory data (will be persisted)
# ==============================
teams: List[Dict[str, Any]] = []           # finalized teams
pending_payments: Dict[str, Dict[str, Any]] = {}  # user_id -> { proof, type, number, username }
collecting: Dict[str, Dict[str, Any]] = {}  # user_id -> { stage, clan, tag, country }
is_open: bool = False

# Conversation states (for proof/type input only)
PROOF = 0

# Duplicate prevention: keep keys "user_id:callback_data"
SEEN_CALLBACKS = set()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================
# Persistence
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
        logger.exception("save_all failed")

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
        logger.exception("load_all failed")

# ==============================
# Keyboards / UI
# ==============================
def kb_player_home() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("📜 القوانين", callback_data="player:rules")],
        [InlineKeyboardButton("📝 التسجيل", callback_data="player:register")],
        [InlineKeyboardButton("📢 قناة الفاينل", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")],
        # زر START دائم في الأسفل كما طلبت
        [InlineKeyboardButton("/start 🔄 إعادة تشغيل البوت", callback_data="player:start_reset")]
    ]
    return InlineKeyboardMarkup(kb)

def kb_admin_home() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🟢 فتح التسجيل", callback_data="admin:open"),
         InlineKeyboardButton("🔴 إغلاق التسجيل", callback_data="admin:close")],
        [InlineKeyboardButton("📥 الطلبات المعلقة", callback_data="admin:view_pending")],
        [InlineKeyboardButton("📋 عرض اللستة", callback_data="admin:view_teams")],
        [InlineKeyboardButton("📣 نشر اللستة الآن", callback_data="admin:publish")],
        [InlineKeyboardButton("/start 🔄 إعادة تشغيل البوت", callback_data="player:start_reset")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_action_buttons(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ قبول", callback_data=f"admin:accept:{user_id}"),
         InlineKeyboardButton("❌ رفض", callback_data=f"admin:reject:{user_id}")]
    ])

# ==============================
# Texts
# ==============================
WELCOME_PLAYER = (
    "🔥 *أهلًا بيك بـ RAGEBACK ESPORT — Finals Manager* 🔥\n\n"
    "هنا تكمّل تسجيل فريقك للفاينلات بطريقة سهلة وسريعة:\n"
    "1) اطّلع على القوانين\n"
    "2) سجل فريقك وأرسل نوع الرصيد مع رقم البطاقة (مثال: `زين 1234567890`)\n"
    "3) انتظر موافقة الإدارة ثم أكمل بيانات الكلان (اسم الكلان، التاغ، علم الدولة كإيموجي 🇮🇶)\n\n"
    "حظًا موفقًا! 🍀"
)

WELCOME_ADMIN = (
    "🛠️ *لوحة تحكم الأدمن — RAGEBACK ESPORT*\n\n"
    "من هنا تفتح/تقفل التسجيل، تراجع الطلبات، وتنشر اللستة."
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
        uname = f"@{e.get('username')}" if e.get("username") else f"ID:{e['user_id']}"
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
# Helpers
# ==============================
async def try_send_sticker(context: ContextTypes.DEFAULT_TYPE, chat_id: int, sticker_id: str):
    if not sticker_id:
        return
    try:
        await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_id)
    except Exception:
        pass

def is_dup(user_id: int, callback_data: str) -> bool:
    key = f"{user_id}:{callback_data}"
    if key in SEEN_CALLBACKS:
        return True
    SEEN_CALLBACKS.add(key)
    return False

def normalize_wallet(txt: str) -> str:
    t = (txt or "").strip().lower().replace(" ", "")
    zain = {"زين", "زينكاش", "zain", "zaincash", "zain-cash"}
    athe = {"أثير", "اثير", "atheir", "athe", "ather"}
    asia = {"آسياسيل", "اسياسيل", "asiacell", "asia-cell", "asiacel"}
    if t in zain:
        return "زين"
    if t in athe:
        return "أثير"
    if t in asia:
        return "آسيا سيل"
    return ""

# ==============================
# START handler
# ==============================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = (user.id == ADMIN_CHAT_ID)
    # send logo if exists
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

# "Start" bottom button -> reset view
async def start_reset_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    # prevent rapid double-handling
    if is_dup(q.from_user.id, q.data):
        await q.answer()
        return
    await q.answer()
    # reuse start_cmd to show interface again
    # build a fake update.message to let start_cmd send reply_photo / reply_text correctly
    await start_cmd(update, context)

# ==============================
# Player callbacks & registration
# ==============================
async def player_rules_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if is_dup(q.from_user.id, q.data):
        await q.answer()
        return
    await q.answer()
    await q.message.reply_text(RULES_TEXT(), parse_mode="Markdown")

async def player_register_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if is_dup(q.from_user.id, q.data):
        await q.answer()
        return ConversationHandler.END
    await q.answer()
    global is_open
    if not is_open:
        await q.message.reply_text("⚠️ التسجيل مغلق الآن. انتظر فتح التسجيل من الإدارة.")
        return ConversationHandler.END
    await q.message.reply_text(
        "🔔 *خطوة إثبات الدفع*\n\n"
        "أرسل نوع الرصيد مع رقم البطاقة (مثال):\n`زين 1234567890` أو `أثير 9876543210`.\n"
        "سيصل الطلب للأدمن للموافقة أو الرفض.",
        parse_mode="Markdown"
    )
    return PROOF

async def register_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # allows using /register from chat
    global is_open
    if not is_open:
        await update.message.reply_text("⚠️ التسجيل مغلق الآن.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔔 *أرسل نوع الرصيد مع رقم البطاقة الآن* (مثل: `زين 1234567890`).",
        parse_mode="Markdown"
    )
    return PROOF

# accept text like "زين 12345" or just "زين"
async def proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pending_payments
    user = update.effective_user
    if not is_open:
        await update.message.reply_text("⚠️ التسجيل مغلق الآن.")
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("⚠️ الرجاء إرسال نوع الرصيد (مثل: زين 12345).")
        return PROOF

    parts = text.split(maxsplit=1)
    typ_raw = parts[0]
    wallet_type = normalize_wallet(typ_raw)
    wallet_number = parts[1].strip() if len(parts) > 1 else ""

    if not wallet_type:
        await update.message.reply_text("⚠️ الرجاء كتابة نوع الرصيد الصحيح: زين / أثير / آسيا سيل")
        return PROOF

    # store pending payment (number optional)
    pending_payments[str(user.id)] = {
        "proof": text,
        "type": wallet_type,
        "number": wallet_number,
        "username": user.username or user.first_name
    }
    save_all()

    await update.message.reply_text("✅ تم استلام الرصيد. طلبك بانتظار مراجعة الإدارة.")

    # notify admin with action buttons
    admin_msg = (
        f"📥 *طلب تسجيل جديد*\n\n"
        f"من: @{user.username or user.first_name}\n"
        f"UserID: `{user.id}`\n\n"
        f"نوع الرصيد: *{wallet_type}*\n"
        f"الرقم: `{wallet_number or '—'}`"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown",
                                       reply_markup=admin_action_buttons(user.id))
    except Exception:
        logger.exception("notify admin failed")

    return ConversationHandler.END

# ==============================
# Admin callbacks
# ==============================
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if is_dup(q.from_user.id, q.data):
        await q.answer()
        return
    await q.answer()
    caller = q.from_user
    if caller.id != ADMIN_CHAT_ID:
        await q.message.reply_text("❌ هذا الزر محجوز للإدارة فقط.")
        return

    data = q.data  # example: admin:open or admin:accept:12345
    parts = data.split(":")
    action = parts[1] if len(parts) >= 2 else ""

    global is_open, pending_payments, collecting, teams

    # admin actions
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

    if action == "view_pending":
        text = build_pending_preview()
        # build per-request accept/reject buttons (limit to 15 to be safe)
        rows = []
        count = 0
        for uid in list(pending_payments.keys()):
            if count >= 15:
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
        await q.message.reply_text(build_list_text(), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 رجوع", callback_data="admin:back_home")]
        ]))
        return

    if action == "publish":
        text = build_list_text()
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
            await q.message.reply_text("✅ تم نشر اللستة في القناة.")
        except Exception:
            logger.exception("publish failed")
            await q.message.reply_text("⚠️ خطأ عند نشر اللستة.")
        return

    if action == "back_home":
        await q.message.reply_text("🏠 الرجوع للوحة الأدمن:", reply_markup=kb_admin_home())
        return

    # accept / reject single user
    if action in ("accept", "reject") and len(parts) == 3:
        target_id = parts[2]
        pending = pending_payments.get(str(target_id))
        if not pending:
            await q.message.reply_text("⚠️ لا يوجد طلب دفع معلق لهذا المستخدم.")
            return

        if action == "reject":
            # notify user
            try:
                await context.bot.send_message(chat_id=int(target_id),
                                               text="❌ تم رفض إثبات الدفع. يرجى التأكد وإعادة المحاولة.")
            except Exception:
                logger.exception("failed notify reject")
            pending_payments.pop(str(target_id), None)
            save_all()
            await q.message.reply_text(f"❌ تم رفض طلب UserID: {target_id}.")
            return

        # accept -> ask user to send clan name next
        try:
            await context.bot.send_message(chat_id=int(target_id),
                                           text="✅ تم قبول إثبات الدفع. الآن أرسل *اسم الكلان الرسمي* (مثال: RageBack).",
                                           parse_mode="Markdown")
        except Exception:
            logger.exception("failed notify accept")
        # move from pending to collecting state
        collecting[str(target_id)] = {"stage": "clan"}
        pending_payments.pop(str(target_id), None)
        save_all()
        await q.message.reply_text(f"✅ تم قبول طلب UserID: {target_id}. تم إشعار المستخدم لبدء إدخال بيانات الكلان.")
        return

    await q.message.reply_text("⚠️ إجراء غير معروف.")

# ==============================
# Collect clan/tag/country from user after admin accept
# ==============================
async def collect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in collecting:
        # not in collecting mode — ignore (or could be other chat text)
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
        await update.message.reply_text("🏳️ الآن أرسل *علم الدولة* كإيموجي فقط (مثال: 🇮🇶).", parse_mode="Markdown")
        return

    if stage == "country":
        if not text:
            await update.message.reply_text("🙁 رجاءً أرسل علم الدولة كإيموجي (مثل 🇮🇶).")
            return
        # store country (we accept emoji or text, as user asked prefer emoji)
        collecting[uid]["country"] = text

        # finalize registration: add to teams if slot available
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

        # notify all registered teams with updated list
        list_text = build_list_text()
        for e in teams:
            try:
                await context.bot.send_message(chat_id=e["user_id"], text=list_text, parse_mode="Markdown")
            except Exception:
                logger.exception(f"notify user {e['user_id']} failed")

        # if filled up, close and announce
        if len(teams) >= MAX_TEAMS:
            is_open = False
            save_all()
            try:
                final_text = "*✅ الاكتفاء: تم إغلاق التسجيل — اللستة النهائية*\n\n" + build_list_text()
                await context.bot.send_message(chat_id=CHANNEL_ID, text=final_text, parse_mode="Markdown")
            except Exception:
                logger.exception("publish final list failed")
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text="✅ العدد اكتمل. تم نشر اللستة النهائية في القناة.")
            except Exception:
                logger.exception("notify admin completion failed")
        return

# ==============================
# Status / utility commands
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
# Boot / Handlers registration
# ==============================
def main():
    load_all()
    if not BOT_TOKEN:
        raise RuntimeError("8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")

    app = Application.builder().token(BOT_TOKEN).build()

    # Basic commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("my_slot", my_slot_cmd))
    app.add_handler(CommandHandler("admin_panel", admin_panel_cmd))
    app.add_handler(CommandHandler("register", register_cmd))

    # CallbackQuery handlers
    app.add_handler(CallbackQueryHandler(start_reset_cb, pattern="^player:start_reset$"))
    app.add_handler(CallbackQueryHandler(player_rules_cb, pattern="^player:rules$"))
    app.add_handler(CallbackQueryHandler(player_register_cb, pattern="^player:register$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))

    # Conversation for proof/type (entry via /register or player_register_cb)
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

    # Handler to collect clan/tag/country (active whenever collecting[user_id] exists)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_handler))

    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()