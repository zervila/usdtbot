import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes, ConversationHandler, \
    MessageHandler as MessageHandlerConv
import requests

# Состояния для ConversationHandler
CONVERT_AMOUNT = range(1)

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Отключаем логи httpx и telegram для безопасности токена
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

# Получение токена из Secrets
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set in Secrets")
    raise ValueError("BOT_TOKEN not set")

def get_crypto_rate(crypto_symbol):
    """Получает курс криптовалюты к KZT через CoinGecko API"""
    try:
        # Мапинг символов к ID CoinGecko
        crypto_ids = {
            'USDT': 'tether',
            'BTC': 'bitcoin', 
            'ETH': 'ethereum',
            'TON': 'the-open-network'
        }
        
        if crypto_symbol not in crypto_ids:
            return None
            
        crypto_id = crypto_ids[crypto_symbol]
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=kzt"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if crypto_id in data and 'kzt' in data[crypto_id]:
            return float(data[crypto_id]['kzt'])
        else:
            raise KeyError(f"Rate not found for {crypto_symbol}")
            
    except (requests.exceptions.RequestException, KeyError, ValueError) as e:
        logger.error(f"CoinGecko API error for {crypto_symbol}: {e}")
        # Универсальный fallback через USD для всех валют
        try:
            url_usd = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd"
            response_usd = requests.get(url_usd, timeout=10)
            response_usd.raise_for_status()
            data_usd = response_usd.json()
            if crypto_id in data_usd and 'usd' in data_usd[crypto_id]:
                usd_rate = float(data_usd[crypto_id]['usd'])
                url_kzt = "https://api.exchangerate-api.com/v4/latest/USD"
                response_kzt = requests.get(url_kzt, timeout=5)
                response_kzt.raise_for_status()
                data_kzt = response_kzt.json()
                if 'rates' in data_kzt and 'KZT' in data_kzt['rates']:
                    kzt_rate = float(data_kzt['rates']['KZT'])
                    return usd_rate * kzt_rate
                else:
                    raise KeyError("KZT rate not found in fallback API")
            else:
                raise KeyError(f"USD rate not found for {crypto_symbol}")
        except (requests.exceptions.RequestException, KeyError, ValueError) as fallback_e:
            logger.error(f"Fallback API error for {crypto_symbol}: {fallback_e}")
            return None

def get_usdt_kzt_rate():
    """Получает курс USDT к KZT"""
    return get_crypto_rate('USDT')

def get_all_rates():
    """Получает курсы всех криптовалют к KZT"""
    rates = {}
    for crypto in ['USDT', 'BTC', 'ETH', 'TON']:
        rate = get_crypto_rate(crypto)
        if rate:
            rates[crypto] = rate
    return rates

def get_reply_keyboard():
    """Создаёт ReplyKeyboardMarkup с кнопками для всех криптовалют и конвертацией"""
    keyboard = [
        [KeyboardButton("USDT/KZT"), KeyboardButton("BTC/KZT")],
        [KeyboardButton("ETH/KZT"), KeyboardButton("TON/KZT")],
        [KeyboardButton("Все курсы"), KeyboardButton("Конвертировать USDT")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start - показывает все курсы и клавиатуру"""
    try:
        rates = get_all_rates()
        if rates:
            message = "Добро пожаловать! 👋\n\nАктуальные курсы:\n\n"
            for crypto, rate in rates.items():
                message += f"1 {crypto} = {rate:.2f} KZT\n"
            logger.info("Start command processed with all rates")
        else:
            message = "Добро пожаловать! 👋\n\nНе удалось получить курсы. Попробуйте позже."
            logger.warning("Start command processed but failed to fetch rates")
        
        await update.message.reply_text(
            message,
            reply_markup=get_reply_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def convert_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запускает процесс конвертации, запрашивает сумму"""
    await update.message.reply_text(
        "Введите количество USDT для конвертации (например, 100):",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Отмена")]], resize_keyboard=True)
    )
    return CONVERT_AMOUNT

async def convert_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает введённую сумму и возвращает результат конвертации"""
    user_input = update.message.text
    if user_input == "Отмена":
        await update.message.reply_text(
            "Конвертация отменена.",
            reply_markup=get_reply_keyboard()
        )
        return ConversationHandler.END

    try:
        amount = float(user_input)
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")
        
        rate = get_crypto_rate('USDT')
        if rate:
            converted_amount = amount * rate
            response = f"{amount} USDT = {converted_amount:.2f} KZT (по курсу 1 USDT = {rate:.2f} KZT)"
            logger.info(f"Converted {amount} USDT to {converted_amount:.2f} KZT")
        else:
            response = "Не удалось получить курс USDT для конверсии. Попробуйте позже."
            logger.warning("Failed to fetch USDT rate for conversion")
        
        await update.message.reply_text(response, reply_markup=get_reply_keyboard())
        return ConversationHandler.END
    except ValueError as e:
        await update.message.reply_text(
            f"Неверный формат суммы. Введите число (например, 100). Ошибка: {e}",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Отмена")]], resize_keyboard=True)
        )
        return CONVERT_AMOUNT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет процесс конвертации"""
    await update.message.reply_text(
        "Конвертация отменена.",
        reply_markup=get_reply_keyboard()
    )
    return ConversationHandler.END

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик всех сообщений"""
    try:
        message_text = update.message.text
        
        # Обработка кнопок для отдельных криптовалют
        if message_text == "USDT/KZT":
            rate = get_crypto_rate('USDT')
            response = f"Актуальный курс: 1 USDT = {rate:.2f} KZT" if rate else "Не удалось получить курс USDT. Попробуйте позже."
            logger.info("USDT rate requested")
            
        elif message_text == "BTC/KZT":
            rate = get_crypto_rate('BTC')
            response = f"Актуальный курс: 1 BTC = {rate:.2f} KZT" if rate else "Не удалось получить курс BTC. Попробуйте позже."
            logger.info("BTC rate requested")
            
        elif message_text == "ETH/KZT":
            rate = get_crypto_rate('ETH')
            response = f"Актуальный курс: 1 ETH = {rate:.2f} KZT" if rate else "Не удалось получить курс ETH. Попробуйте позже."
            logger.info("ETH rate requested")
            
        elif message_text == "TON/KZT":
            rate = get_crypto_rate('TON')
            response = f"Актуальный курс: 1 TON = {rate:.2f} KZT" if rate else "Не удалось получить курс TON. Попробуйте позже."
            logger.info("TON rate requested")
            
        elif message_text == "Все курсы":
            rates = get_all_rates()
            if rates:
                response = "Актуальные курсы:\n\n"
                for crypto, rate in rates.items():
                    response += f"1 {crypto} = {rate:.2f} KZT\n"
                logger.info("All rates requested")
            else:
                response = "Не удалось получить курсы. Попробуйте позже."
                logger.warning("Failed to fetch all rates")
                
        elif message_text == "Конвертировать USDT":
            return  # Передаём управление ConversationHandler
        
        else:
            # Для любого другого сообщения показываем клавиатуру
            response = "Выберите криптовалюту для получения курса или нажмите 'Конвертировать USDT':"
            logger.info("ReplyKeyboard sent successfully")
        
        await update.message.reply_text(response, reply_markup=get_reply_keyboard())
        
    except Exception as e:
        logger.error(f"Error sending keyboard: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Запуск бота с поллингом"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Настраиваем ConversationHandler для конвертации
        conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^(Конвертировать USDT)$"), convert_start)],
            states={
                CONVERT_AMOUNT: [MessageHandlerConv(filters.TEXT & ~filters.COMMAND, convert_amount)]
            },
            fallbacks=[MessageHandler(filters.Regex("^(Отмена)$"), cancel)]
        )
        
        # Добавляем основные обработчики
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(conv_handler)
        
        logger.info("Bot starting with polling...")
        
        # Запускаем поллинг с drop_pending_updates=True для избежания конфликтов
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")

if __name__ == '__main__':
    main()
