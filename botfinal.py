# botfinal_complete_fixed.py
import os
import json
import logging
from typing import Dict, Any, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
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
# إعدادات
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "6005239475"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@RAGEBACKESPORT")
LOGO_PATH = os.getenv("LOGO_PATH", "logo.jpg")
MAX_TEAMS = int(os.getenv("MAX_TEAMS", "20"))

STICKER_WELCOME = os.getenv("STICKER_WELCOME", "")
STICKER_ADMIN = os.getenv("STICKER_ADMIN", "")

DATA_FILE = os.getenv("DATA_FILE", "bot_data.json")

# بيانات البوت
teams: List[Dict[str, Any]] = []
pending_payments: Dict[str, Dict[str, Any]] = {}   # user_id -> {type, card, username}
wallet_collecting: Dict[str, Dict[str, Any]] = {}  # user_id -> {"stage": "wallet"/"number", "wallet": ...}
collecting: Dict[str, Dict[str, Any]] = {}         # user_id -> clan collection after admin accept
is_open: bool = False

# Conversation states
PROOF = 0

# لوغ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================
# حفظ / تحميل البيانات
# ==============================
def save_all():
    try:
        data = {
            "teams": teams,
            "pending_payments": pending_payments,
            "wallet_collecting": wallet_collecting,
            "collecting": collecting,
            "is_open": is_open
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to save data")

def load_all():
    global teams, pending_payments, wallet_collecting, collecting, is_open
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        teams = data.get("teams", [])
        pending_payments = data.get("pending_payments", {})
        wallet_collecting = data.get("wallet_collecting", {})
        collecting = data.get("collecting", {})
        is_open = data.get("is_open", False)
    except Exception:
        logger.exception("Failed to load data")

# ==============================
# لوحات الأزرار
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
# نصوص ثابتة
# ==============================
WELCOME_PLAYER = (
    "🔥 *أهلًا بيك بـ RAGEBACK ESPORT — Finals Manager* 🔥\n\n"
    "1) اطّلع على القوانين\n"
    "2) اضغط تسجيل ثم أرسل نوع الرصيد (زين أو اسيا) ثم رقم البطاقة في رسالة منفصلة\n"
    "3) بعد قبول الإدارة اكمل بيانات الكلان\n"
)

WELCOME_ADMIN = (
    "🛠️ *لوحة تحكم الأدمن — RAGEBACK ESPORT*\n\n"
    "تحكم بالسجلّات والنشر من هنا."
)

RULES_TEXT = lambda: (
    "📜 *قوانين الفاينلات:*\n\n"
    "• الحد الأدنى لمستوى الحساب: *50*\n"
    "• الاحترام واجب — لا سب أو شتم\n"
    "• الحد الأدنى لحجم الفريق: *3 لاعبين*\n"
    f"• كل فاينل يقبل حتى *{MAX_TEAMS}* فريقاً\n"
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
        lines.append(f"{idx}) @{uname} — UserID: `{uid}` — نوع: *{p.get('type','?')}* — البطاقة: `{p.get('card','?')}`")
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
    asia = {"اسيا", "آسياسيل", "asiacell", "asia", "asia-sell", "asiasell"}
    if t in zain:
        return "زين"
    if t in asia:
        return "اسيا"
    return ""

# ==============================
# أوامر وواجهات المستخدم
# ==============================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = (user and user.id == ADMIN_CHAT_ID)
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

async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES_TEXT(), parse_mode="Markdown")

async def register_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_open
    if not is_open:
        await update.message.reply_text("⚠️ التسجيل مغلق الآن.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔔 *خطوة تسجيل الرصيد*\n\n"
        "أرسل الآن نوع الرصيد فقط: *زين* أو *اسيا*.\n"
        "بعدها أرسل رقم البطاقة في رسالة منفصلة.",
        parse_mode="Markdown"
    )
    return PROOF

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 الحالة: {'مفتوح' if is_open else 'مغلق'}\nعدد الفرق: {len(teams)} / {MAX_TEAMS}")

async def my_slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    for e in teams:
        if e["user_id"] == user.id or str(e["user_id"]) == str(user.id):
            await update.message.reply_text(f"📍 موقع فريقك: {e['slot']} — {e['clan']} | {e['tag']} | {e['country']}")
            return
    await update.message.reply_text("ℹ️ لم تُسجّل في اللستة الحالية.")

async def admin_panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("هذا الأمر مخصّص للأدمن فقط.")
        return
    await update.message.reply_text("لوحة تحكم الأدمن:", reply_markup=kb_admin_home())
    await try_send_sticker(context, update.effective_chat.id, STICKER_ADMIN)

# ==============================
# أزرار اللاعب (CallbackQuery)
# ==============================
async def player_rules_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(RULES_TEXT(), parse_mode="Markdown")

async def player_register_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    global is_open
    if not is_open:
        # نعدل الرسالة (لوحة اللاعب) أو نرد
        try:
            await q.edit_message_text("⚠️ التسجيل مغلق الآن. انتظر فتح التسجيل من الإدارة.", reply_markup=kb_player_home())
        except Exception:
            await q.message.reply_text("⚠️ التسجيل مغلق الآن. انتظر فتح التسجيل من الإدارة.")
        return ConversationHandler.END
    # نبدأ Conversation لالتقاط نوع الرصيد
    try:
        await q.edit_message_text(
            "🔔 *خطوة تسجيل الرصيد*\n\n"
            "أرسل الآن نوع الرصيد فقط: *زين* أو *اسيا*.\n"
            "بعدها أرسل رقم البطاقة في رسالة منفصلة.",
            parse_mode="Markdown"
        )
    except Exception:
        await q.message.reply_text(
            "🔔 *خطوة تسجيل الرصيد*\n\n"
            "أرسل الآن نوع الرصيد فقط: *زين* أو *اسيا*.\n"
            "بعدها أرسل رقم البطاقة في رسالة منفصلة.",
            parse_mode="Markdown"
        )
    return PROOF

# ==============================
# استقبال نوع الرصيد (مراحل: نوع -> رقم)
# ==============================
async def proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global wallet_collecting, pending_payments
    user = update.effective_user
    uid = str(user.id)
    text = (update.message.text or "").strip()

    # هل العميل في مرحلة إدخال رقم البطاقة؟
    stage = wallet_collecting.get(uid, {}).get("stage")

    if not stage:
        # هذه الرسالة متوقعة أن تكون اسم الرصيد
        wallet = normalize_wallet(text)
        if not wallet:
            await update.message.reply_text("⚠️ الرجاء إرسال نوع الرصيد الصحيح فقط: زين أو اسيا")
            return PROOF
        # خزن المرحلة واطلب رقم البطاقة
        wallet_collecting[uid] = {"stage": "number", "wallet": wallet}
        save_all()
        await update.message.reply_text(f"✳️ نوع الرصيد مسجّل: *{wallet}*\nالآن أرسل رقم البطاقة (في رسالة منفصلة).", parse_mode="Markdown")
        return PROOF

    # مرحلة استقبال رقم البطاقة
    if stage == "number":
        wallet = wallet_collecting[uid]["wallet"]
        card_number = text
        # يمكنك هنا إضافة فلترة على صيغة الرقم إن أردت (أرقام فقط)، لكن تركتها مرنة كما طلبت
        pending_payments[uid] = {
            "type": wallet,
            "card": card_number,
            "username": user.username or user.first_name
        }
        # أزل حالة التقاط الرصيد
        wallet_collecting.pop(uid, None)
        save_all()

        # أبلغ المستخدم مباشرة
        await update.message.reply_text("✅ تم إرسال طلبك للإدارة. انتظر الموافقة.")

        # أرسل للأدمن رسالة واحدة تحتوي النوع والرقم مع أزرار القبول/الرفض
        admin_msg = (
            f"📥 *طلب تسجيل جديد*\n\n"
            f"من: @{user.username or user.first_name}\n"
            f"UserID: `{uid}`\n\n"
            f"نوع الرصيد: *{wallet}*\n"
            f"رقم البطاقة: `{card_number}`\n\n"
            f"اضغط قبول أو رفض أسفل."
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
# أزرار الأدمن (CallbackQuery) — الآن نستخدم edit_message_text لتفادي تكرار
# ==============================
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    caller = q.from_user

    if caller.id != ADMIN_CHAT_ID:
        try:
            await q.edit_message_text("❌ هذا الزر محجوز للإدارة فقط.")
        except Exception:
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
                await q.edit_message_text("⚠️ لا يوجد طلب معلّق لهذا المستخدم.", reply_markup=kb_admin_home())
                return

            if action == "reject":
                # بلغ المستخدم بالرفض
                try:
                    await context.bot.send_message(chat_id=int(target_id),
                                                   text="❌ تم رفض طلب التسجيل. تأكد من البيانات وحاول مرة أخرى.")
                except Exception:
                    logger.exception("Failed to send reject message to user")
                pending_payments.pop(str(target_id), None)
                save_all()
                await q.edit_message_text(f"❌ تم رفض طلب UserID: {target_id}.", reply_markup=kb_admin_home())
                return

            # قبول: اطلب من المستخدم بيانات الكلان (نبدأ وضع collecting)
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
        try:
            await q.edit_message_text("⚠️ حدث خطأ أثناء تنفيذ الأمر.", reply_markup=kb_admin_home())
        except Exception:
            pass
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
        save_all()
        await update.message.reply_text("✳️ تم تسجيل اسم الكلان. الآن أرسل *التاج الرسمي* للفريق.")
        return

    if stage == "tag":
        if not text:
            await update.message.reply_text("🙁 رجاءً أرسل *تاج الفريق* نصًّا.")
            return
        collecting[uid]["tag"] = text
        collecting[uid]["stage"] = "country"
        save_all()
        await update.message.reply_text("✳️ تم تسجيل التاج. الآن أرسل *إيموجي العلم* للدولة (مثال 🇮🇶).")
        return

    if stage == "country":
        if not text:
            await update.message.reply_text("🙁 رجاءً أرسل *إيموجي العلم* للدولة (مثال 🇮🇶).")
            return
        collecting[uid]["country"] = text

        # تحقق المساحة ثم إضافة الفريق
        if len(teams) >= MAX_TEAMS:
            collecting.pop(uid, None)
            save_all()
            await update.message.reply_text("⚠️ آسف، العدد اكتمل ولا يمكن إضافة فريقك الآن.")
            return

        slot = len(teams) + 1
        new_team = {
            "slot": slot,
            "user_id": int(uid),
            "username": user.username or user.first_name,
            "clan": collecting[uid]["clan"],
            "tag": collecting[uid]["tag"],
            "country": collecting[uid]["country"]
        }
        teams.append(new_team)
        collecting.pop(uid, None)
        save_all()

        await update.message.reply_text(f"✅ تم تسجيل فريقك بنجاح في اللستة. رقم الفريق: {slot}")
        # أبلغ جميع المسجلين بالقائمة المحدثة
        list_text = build_list_text()
        for e in teams:
            try:
                await context.bot.send_message(chat_id=e["user_id"], text=list_text, parse_mode="Markdown")
            except Exception:
                logger.exception(f"Failed to notify user {e['user_id']} about updated list")
        # إذا اكتمل العدد، أغلق ونشر
        if len(teams) >= MAX_TEAMS:
            global is_open
            is_open = False
            save_all()
            try:
                final_text = "*✅ الاكتفاء: تم إغلاق التسجيل — اللستة النهائية*\n\n" + build_list_text()
                await context.bot.send_message(chat_id=CHANNEL_ID, text=final_text, parse_mode="Markdown")
            except Exception:
                logger.exception("Failed to publish final list to channel")
        return

# ==============================
# تسجيل الهاندلرز وتشغيل البوت
# ==============================
def main():
    load_all()
    if not BOT_TOKEN:
        raise RuntimeError("8001395532:AAE4X5EdQ4whYdNdnt00fCeeb8g9aDCKHqU")
    app = Application.builder().token(BOT_TOKEN).build()

    # أوامر عامة
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("register", register_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("my_slot", my_slot_cmd))
    app.add_handler(CommandHandler("admin_panel", admin_panel_cmd))

    # callback handlers
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))
    app.add_handler(CallbackQueryHandler(player_rules_cb, pattern="^player:rules$"))
    app.add_handler(CallbackQueryHandler(player_register_cb, pattern="^player:register$"))

    # Conversation: نبدأ عند ضغط زر التسجيل أو أمر /register
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

    # جمع بيانات الكلان (تعمل فقط للمستخدمين في collecting)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_handler))

    # ابدأ البوت
    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()