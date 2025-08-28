# rageback_premium_bot.py
import logging, os, re
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    ConversationHandler, CallbackQueryHandler, filters
)

# ========= إعدادات عامة =========
BOT_TOKEN = os.getenv("8465165595:AAE91ipzTJBaQk9UQeboM72UV3c8mtNPHp4")
ADMIN_CHAT_ID = int(os.getenv("6005239475"))
LOGO_PATH = os.getenv("LOGO_PATH", "logo.jpg")
ADMIN_INVITE_LINK = os.getenv("https://t.me/+O4ltDsSroClmNGRi")  

# ========= تسجيل =========
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ========= حالات المحادثة =========
(NAME, IGN, IDGAME, AGE, ACC_LEVEL, REGION, RANK, EXP, CONFIRM) = range(9)

# ========= نصوص =========
WELCOME_CAPTION = (
    "🔥✨ أهلاً وسهلاً بك في *RAGEBACK ESPORT* ✨🔥\n\n"
    "🏆 حيثُ نصنع الأساطير ولا نبحث عنها.\n"
    "⚔️ هنا تبدأ رحلتك نحو التحدي، الانتصار، والمجد.\n\n"
    "📖 اطلع على القوانين أولاً.\n"
    "📝 بعدها قدّم طلبك للانضمام.\n"
    "🚀 المستقبل يبدأ من هنا... مع *RAGEBACK*!"
)

RULES_PAGES = [
    "📖 *قوانين RAGEBACK — 1/3*\n\n"
    "1️⃣ العمر لا يقل عن 16 سنة.\n"
    "2️⃣ مستوى الحساب لا يقل عن 50.\n"
    "3️⃣ الاحترام واجب، ويُمنع السب والقذف.\n"
    "4️⃣ يُمنع استخدام الغش/الهاكات/البرامج المساعدة.\n",
    "📖 *قوانين RAGEBACK — 2/3*\n\n"
    "5️⃣ الالتزام بمواعيد التدريبات والبطولات.\n"
    "6️⃣ النشاط وعدم التغيب بدون عذر.\n"
    "7️⃣ احترام قرارات الإدارة بشكل كامل.\n"
    "8️⃣ اللعب بروح الفريق والتعاون.\n",
    "📖 *قوانين RAGEBACK — 3/3*\n\n"
    "9️⃣ أي مخالفة جسيمة = إنذار/طرد مباشر.\n"
    "🔟 يمنع نشر روابط خارجية دون إذن.\n"
    "♻️ القوانين قابلة للتحديث بما يخدم مصلحة الفريق.\n\n"
    "انتهيت؟ اضغط زر *رجوع* للعودة إلى القائمة."
]

APPLY_INTRO = (
    "✍️ *سنبدأ نموذج التقديم الآن* — أجب خطوة بخطوة.\n"
    "يمكنك الإلغاء في أي وقت بكتابة /cancel.\n\n"
    "ما اسمك الحقيقي الكامل؟"
)

CONTACT_TEXT = "📩 للتواصل مع الإدارة: @YourContactHere"

# ========= كيبورد =========
def kb_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 القوانين", callback_data="rules:1")],
        [InlineKeyboardButton("📝 تقديم طلب", callback_data="apply:start")],
        [InlineKeyboardButton("📩 تواصل", callback_data="contact")]
    ])

def kb_start():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 انطلق", callback_data="open_menu")]
    ])

def kb_rules_nav(page: int):
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⏮️ السابق", callback_data=f"rules:{page-1}"))
    if page < len(RULES_PAGES):
        buttons.append(InlineKeyboardButton("⏭️ التالي", callback_data=f"rules:{page+1}"))

    rows = []
    if buttons:
        rows.append(buttons)
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="back")])
    return InlineKeyboardMarkup(rows)

def kb_confirm_submission(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ إرسال", callback_data="apply:send")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="apply:cancel")]
    ])

def kb_admin_actions(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ قبول", callback_data=f"admin:accept:{user_id}"),
         InlineKeyboardButton("❌ رفض", callback_data=f"admin:reject:{user_id}")]
    ])

# ========= post_init =========
async def post_init(application: Application):
    commands = [
        BotCommand("start", "ابدأ | Start"),
        BotCommand("rules", "القوانين"),
        BotCommand("apply", "تقديم طلب"),
        BotCommand("contact", "تواصل"),
        BotCommand("cancel", "إلغاء التقديم")
    ]
    await application.bot.set_my_commands(commands)

# ========= أوامر =========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة البداية مع اللوغو وزر انطلق فقط"""
    if update.message:
        if os.path.exists(LOGO_PATH):
            with open(LOGO_PATH, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo, caption=WELCOME_CAPTION, parse_mode="Markdown", reply_markup=kb_start()
                )
        else:
            await update.message.reply_text(WELCOME_CAPTION, parse_mode="Markdown", reply_markup=kb_start())

async def cb_open_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("اختر من القائمة:", reply_markup=kb_main_menu())

async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES_PAGES[0], parse_mode="Markdown", reply_markup=kb_rules_nav(1))

async def cmd_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(CONTACT_TEXT)

# ========= القوانين =========
async def cb_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    page = int(q.data.split(":")[1])
    page = max(1, min(page, len(RULES_PAGES)))
    await q.message.reply_text(RULES_PAGES[page-1], parse_mode="Markdown", reply_markup=kb_rules_nav(page))

async def cb_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("عدنا للقائمة الرئيسية:", reply_markup=kb_main_menu())

# ========= محادثة التقديم =========
def is_int(text: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}", text.strip()))

async def cmd_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(APPLY_INTRO, parse_mode="Markdown")
    return NAME

async def cb_apply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(APPLY_INTRO, parse_mode="Markdown")
    return NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("🎮 ما *اسمك داخل اللعبة (IGN)*؟", parse_mode="Markdown")
    return IGN

async def ask_ign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ign"] = update.message.text.strip()
    await update.message.reply_text("🆔 ما هو *ID اللعبة*؟", parse_mode="Markdown")
    return IDGAME

async def ask_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["idgame"] = update.message.text.strip()
    await update.message.reply_text("📅 كم *عمرك*؟ (أرقام فقط)", parse_mode="Markdown")
    return AGE

async def ask_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    age_txt = update.message.text.strip()
    if not is_int(age_txt):
        await update.message.reply_text("❗ الرجاء إدخال العمر بالأرقام فقط (مثال: 18).")
        return AGE
    age = int(age_txt)
    context.user_data["age"] = age
    if age < 16:
        await update.message.reply_text("⚠️ الحد الأدنى للعمر 16 سنة. إن كنت قريبًا من السن المطلوب يمكنك الاستمرار وسيتم تقييم حالتك.")
    await update.message.reply_text("📈 ما هو *مستوى حسابك*؟ (أرقام فقط)", parse_mode="Markdown")
    return ACC_LEVEL

async def ask_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lvl_txt = update.message.text.strip()
    if not is_int(lvl_txt):
        await update.message.reply_text("❗ الرجاء إدخال المستوى بالأرقام فقط (مثال: 55).")
        return ACC_LEVEL
    lvl = int(lvl_txt)
    context.user_data["level"] = lvl
    if lvl < 50:
        await update.message.reply_text("⚠️ الحد الأدنى للمستوى 50. يمكنك الاستمرار وسيتم تقييم طلبك.")
    await update.message.reply_text("🌍 من أي *دولة/منطقة* أنت؟", parse_mode="Markdown")
    return REGION

async def ask_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["region"] = update.message.text.strip()
    await update.message.reply_text("⚔️ اذكر *اللعبة* التي تلعبها و*رتبتك/مستواك*؟", parse_mode="Markdown")
    return RANK

async def ask_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["rank"] = update.message.text.strip()
    await update.message.reply_text("🏆 هل لديك *خبرات سابقة* أو فرق لعبت معها؟ (اكتب لا يوجد إذا ما عندك)", parse_mode="Markdown")
    return EXP

async def ask_exp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["exp"] = update.message.text.strip()
    d = context.user_data
    summary = (
        "✅ *تأكيد بيانات التقديم:*\n\n"
        f"👤 الاسم: {d['name']}\n"
        f"🎮 IGN: {d['ign']}\n"
        f"🆔 ID: {d['idgame']}\n"
        f"📅 العمر: {d['age']}\n"
        f"📈 المستوى: {d['level']}\n"
        f"🌍 الدولة: {d['region']}\n"
        f"⚔️ اللعبة/الرتبة: {d['rank']}\n"
        f"🏆 الخبرات: {d['exp']}\n\n"
        "هل تريد إرسال الطلب الآن؟"
    )
    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=kb_confirm_submission(update.message.from_user.id))
    return CONFIRM

async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action = q.data.split(":")[1]  # send | cancel
    if action == "send":
        d = context.user_data
        user = q.from_user
        admin_msg = (
            "📥 *طلب انضمام جديد*\n\n"
            f"👤 الاسم: {d['name']}\n"
            f"🎮 IGN: {d['ign']}\n"
            f"🆔 ID: {d['idgame']}\n"
            f"📅 العمر: {d['age']}\n"
            f"📈 المستوى: {d['level']}\n"
            f"🌍 الدولة: {d['region']}\n"
            f"⚔️ اللعبة/الرتبة: {d['rank']}\n"
            f"🏆 الخبرات: {d['exp']}\n\n"
            f"من: @{user.username or user.id}"
        )
        await q.message.reply_text("✅ تم إرسال طلبك وهو *قيد المراجعة* الآن.", parse_mode="Markdown")
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown", reply_markup=kb_admin_actions(user.id))
    else:
        await q.message.reply_text("❌ تم إلغاء التقديم.")
    context.user_data.clear()
    return ConversationHandler.END

# ========= قرارات الأدمن =========
async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, action, uid_str = q.data.split(":")
    user_id = int(uid_str)

    if action == "accept":
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 مبروك! تم *قبول* طلبك.\n"
                 f"انضم عبر الرابط: {ADMIN_INVITE_LINK}",
            parse_mode="Markdown"
        )
        await q.message.reply_text("✅ تم قبول اللاعب وإرسال الدعوة.")
    elif action == "reject":
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ نعتذر، تم *رفض* طلبك حالياً.",
            parse_mode="Markdown"
        )
        await q.message.reply_text("❌ تم رفض اللاعب.")

# ========= /cancel =========
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("تم الإلغاء. عدنا للقائمة الرئيسية:", reply_markup=kb_main_menu())

# ========= MAIN =========
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # أوامر
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("apply", cmd_apply))
    app.add_handler(CommandHandler("contact", cmd_contact))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # أزرار
    app.add_handler(CallbackQueryHandler(cb_open_menu, pattern="^open_menu$"))
    app.add_handler(CallbackQueryHandler(cb_rules, pattern=r"^rules:\d+$"))
    app.add_handler(CallbackQueryHandler(cb_back, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(cmd_contact, pattern="^contact$"))

    # محادثة التقديم
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("apply", cmd_apply),
            CallbackQueryHandler(cb_apply_start, pattern="^apply:start$")
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            IGN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_ign)],
            IDGAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_id)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_age)],
            ACC_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_level)],
            REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_region)],
            RANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_rank)],
            EXP: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_exp)],
            CONFIRM: [CallbackQueryHandler(finalize, pattern="^apply:(send|cancel)$")],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True
    )
    app.add_handler(conv)

    # قرارات الأدمن
    app.add_handler(CallbackQueryHandler(admin_action, pattern=r"^admin:(accept|reject):\d+$"))

    print("RAGEBACK Premium Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
