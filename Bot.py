from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackContext,
    InlineQueryHandler,
    CallbackQueryHandler,
    filters
)
import requests
import sqlite3
import logging
import os
import uuid

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройка БД
conn = sqlite3.connect('emails.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS user_emails
             (user_id INTEGER PRIMARY KEY,
              email TEXT,
              password TEXT,
              token TEXT,
              email_id TEXT)''')
conn.commit()

API_URL = "https://api.mail.tm/"

def create_user_email(user_id):
    try:
        # Генерация уникального ID для почты
        email_id = str(uuid.uuid4())[:8]
        
        domain_response = requests.get(f"{API_URL}domains").json()
        domain = domain_response['hydra:member'][0]['domain']
        email = f"user_{email_id}@{domain}"
        password = os.urandom(8).hex()

        response = requests.post(
            f"{API_URL}accounts",
            json={"address": email, "password": password}
        )
        if response.status_code != 201:
            return None

        token_response = requests.post(
            f"{API_URL}token",
            json={"address": email, "password": password}
        )
        token = token_response.json().get('token')

        c.execute(
            "INSERT OR REPLACE INTO user_emails VALUES (?, ?, ?, ?, ?)",
            (user_id, email, password, token, email_id)
        )
        conn.commit()
        return email

    except Exception as e:
        logger.error(f"Error: {e}")
        return None

def get_user_emails(user_id):
    c.execute("SELECT token FROM user_emails WHERE user_id=?", (user_id,))
    result = c.fetchone()
    if not result:
        return []
    
    try:
        headers = {"Authorization": f"Bearer {result[0]}"}
        response = requests.get(f"{API_URL}messages", headers=headers)
        return response.json().get('hydra:member', [])
    except Exception as e:
        logger.error(f"Error: {e}")
        return []

def delete_user_email(user_id):
    try:
        c.execute("DELETE FROM user_emails WHERE user_id=?", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error: {e}")
        return False

async def inline_query(update: Update, context: CallbackContext):
    query = update.inline_query.query.strip().lower()
    user_id = update.inline_query.from_user.id
    results = []

    if query == "createmail":
        email = create_user_email(user_id)
        if email:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Проверить почту", callback_data=f"check_{user_id}")],
                [InlineKeyboardButton("❌ Удалить почту", callback_data=f"delete_{user_id}")]
            ])
            
            results.append(InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="Почта создана!",
                input_message_content=InputTextMessageContent(
                    f"📧 Ваша временная почта:\n`{email}`",
                    parse_mode='Markdown'
                ),
                reply_markup=keyboard
            ))

    await update.inline_query.answer(results, cache_time=0)

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if data.startswith("check_"):
        target_user = int(data.split("_")[1])
        if user_id != target_user:
            await query.answer("❌ Доступ запрещен!", show_alert=True)
            return
            
        emails = get_user_emails(user_id)
        if emails:
            response = "📩 Последние письма:\n\n" + "\n".join(
                [f"• {m['subject']} ({m['from']['address']})" for m in emails[:3]]
            )
        else:
            response = "📭 Почта пуста"
        
        await query.edit_message_text(
            f"{query.message.text}\n\n{response}",
            reply_markup=query.message.reply_markup
        )

    elif data.startswith("delete_"):
        target_user = int(data.split("_")[1])
        if user_id != target_user:
            await query.answer("❌ Доступ запрещен!", show_alert=True)
            return
            
        if delete_user_email(user_id):
            await query.edit_message_text("✅ Почта удалена")
        else:
            await query.edit_message_text("❌ Ошибка удаления")

    await query.answer()

def main():
    application = Application.builder().token(os.getenv("BOT_TOKEN")).build()
    
    application.add_handler(InlineQueryHandler(inline_query))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.run_polling()

if __name__ == '__main__':
    if os.path.exists("emails.db"):
        os.remove("emails.db")
    main()
