# rageback_bot.py
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, CallbackQueryHandler, filters
)

# ========= إعدادات =========
BOT_TOKEN = "8465165595:AAE91ipzTJBaQk9UQeboM72UV3c8mtNPHp4"
ADMIN_CHAT_ID = 6005239475

# ========= اللوغو =========
LOGO_PATH = "logo.jpg"  # ضع صورة اللوغو بنفس مجلد الملف

# ========= القوانين =========
RULES_TEXT = (
    "📖 *قوانين الانضمام إلى RAGEBACK ESPORT*\n\n"
    "1️⃣ العمر لا يقل عن 16 سنة.\n"
    "2️⃣ مستوى الحساب لا يقل عن 50.\n"
    "3️⃣ الاحترام التام بين الأعضاء، يمنع السب والقذف.\n"
    "4️⃣ الالتزام بالحضور في التدريبات والبطولات.\n"
    "5️⃣ يمنع استخدام أي غش أو برامج هاك.\n"
    "6️⃣ النشاط واجب وعدم التغيب بدون عذر.\n"
    "7️⃣ احترام قرارات الإدارة بشكل كامل.\n\n"
    "⬇️ اضغط رجوع للعودة إلى القائمة الرئيسية."
)

APPLY_INSTRUCTIONS = (
    "📝 *تعليمات التقديم*\n\n"
    "أرسل رسالة واحدة تتضمن البيانات التالية بالترتيب:\n"
    "1- اسمك الحقيقي الكامل\n"
    "2- اسمك داخل اللعبة (IGN)\n"
    "3- ID اللعبة\n"
    "4- عمرك وتاريخ ميلادك\n"
    "5- الدولة/المنطقة\n"
    "6- اللعبة + الرتبة/المستوى\n"
    "7- خبراتك السابقة (إذا توجد)\n\n"
    "بعد الإرسال ستصلك رسالة تأكيد أن طلبك قيد المراجعة ✅"
)

# ========= أزرار رئيسية =========
def main_menu():
    keyboard = [
        [KeyboardButton("📖 القوانين")],
        [KeyboardButton("📝 تقديم طلب")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def back_button():
    keyboard = [[KeyboardButton("⬅️ رجوع")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ========= أوامر =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(LOGO_PATH, "rb") as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="🔥 *مرحباً بك في RAGEBACK ESPORT* 🔥\n\n"
                    "🏆 حيث نصنع الأساطير، لا نبحث عنها.\n\n"
                    "اختر من القائمة بالأسفل 👇",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "📖 القوانين":
        await update.message.reply_text(RULES_TEXT, parse_mode="Markdown", reply_markup=back_button())

    elif text == "📝 تقديم طلب":
        await update.message.reply_text(APPLY_INSTRUCTIONS, parse_mode="Markdown")

    elif text == "⬅️ رجوع":
        await update.message.reply_text("⬅️ رجعت إلى القائمة الرئيسية:", reply_markup=main_menu())

    else:
        # اعتبر أن هذا تقديم طلب
        user = update.message.from_user
        msg = update.message.text

        confirm = (
            "✅ تم استلام طلبك وهو الآن *قيد المراجعة*.\n"
            "سيتم التواصل معك قريباً عبر الإدارة."
        )
        await update.message.reply_text(confirm, parse_mode="Markdown", reply_markup=main_menu())

        # أرسل نسخة للأدمن
        admin_msg = (
            "📥 *طلب انضمام جديد*\n\n"
            f"👤 من: @{user.username or user.id}\n"
            f"🆔 UserID: {user.id}\n\n"
            f"الطلب:\n{msg}"
        )
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown")

# ========= تشغيل =========
def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
