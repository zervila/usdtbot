import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import requests
import time

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Получение токена из Secrets
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set in Secrets")
    raise ValueError("BOT_TOKEN not set")

def get_usdt_kzt_rate():
    """Получает курс USDT к KZT с Binance API или fallback API"""
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=USDTKZT"
        response = requests.get(url, timeout=5)
        data = response.json()
        return float(data['price'])
    except requests.exceptions.RequestException as e:
        logger.error(f"Binance API error: {e}")
        try:
            url_fallback = "https://api.exchangerate-api.com/v4/latest/USD"
            response = requests.get(url_fallback, timeout=5)
            data = response.json()
            return data['rates']['KZT']  # USD to KZT (USDT ≈ USD)
        except Exception as fallback_e:
            logger.error(f"Fallback API error: {fallback_e}")
            return None

def get_keyboard():
    """Создаёт клавиатуру с одной кнопкой"""
    keyboard = [
        [InlineKeyboardButton("Получить курс", callback_data='get_course')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик всех сообщений, отправляет клавиатуру"""
    try:
        await update.message.reply_text("Выберите действие:", reply_markup=get_keyboard())
        logger.info("Keyboard sent successfully")
    except Exception as e:
        logger.error(f"Error sending keyboard: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопку"""
    query = update.callback_query
    try:
        await query.answer()  # Подтверждаем нажатие
        logger.info(f"Button pressed: {query.data}")

        if query.data == 'get_course':
            rate = get_usdt_kzt_rate()
            if rate:
                message = f"Актуальный курс: 1 USDT = {rate:.2f} KZT"
                logger.info(f"Course sent: {message}")
            else:
                message = "Не удалось получить курс. Попробуйте позже."
                logger.warning("Failed to fetch course")
            await query.edit_message_text(message, reply_markup=get_keyboard())
    except Exception as e:
        logger.error(f"Error handling button: {e}")
        await query.edit_message_text("Произошла ошибка. Попробуйте позже.", reply_markup=get_keyboard())

def main():
    """Запуск бота с поллингом"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
        application.add_handler(CallbackQueryHandler(button_handler))
        logger.info("Bot starting with polling...")
        while True:
            try:
                application.run_polling()
            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(5)  # Задержка перед перезапуском
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")

if __name__ == '__main__':
    main()