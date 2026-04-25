"""
Telegram Pyrogram Session String Generator Bot

The bot owner only needs a BOT_TOKEN.
End users provide their OWN API_ID, API_HASH, phone, login code, and
2-Step Verification password (if any) inside the chat with the bot.
"""

# ============================================================================
# CONFIG  ->  paste your bot token below, then deploy.
# ----------------------------------------------------------------------------
# BOT_TOKEN: get from @BotFather on Telegram
# ============================================================================

BOT_TOKEN = "8770901362:AAE0VcqO2YM6qnA_d8RqUmWnSbC2O3AAwAc"

# Render injects PORT automatically. You do NOT need to change this.
import os
PORT = int(os.environ.get("PORT", "8080"))

# ============================================================================
# Compatibility shim: Python 3.12+ removed the implicit event loop in the
# main thread. Pyrogram 2.0.106's sync wrapper calls asyncio.get_event_loop()
# at import time, which crashes on newer Python. Create a loop explicitly
# BEFORE importing pyrogram.
# ============================================================================

import asyncio

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# ============================================================================
# Start the tiny HTTP server immediately so Render detects an open port even
# if any later import is slow.
# ============================================================================

from threading import Thread
from flask import Flask

flask_app = Flask(__name__)


@flask_app.route("/")
def root():
    return "Telegram session generator bot is running."


@flask_app.route("/healthz")
def healthz():
    return "ok"


def run_web() -> None:
    flask_app.run(host="0.0.0.0", port=PORT, use_reloader=False)


Thread(target=run_web, daemon=True).start()

# ============================================================================
# Bot code  ->  no need to edit anything below.
# ============================================================================

import logging

from pyrogram import Client
from pyrogram.errors import (
    ApiIdInvalid,
    FloodWait,
    PasswordHashInvalid,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
)
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger("session-bot")

# Conversation states
API_ID, API_HASH, PHONE, CODE, PASSWORD = range(5)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["/generate"], ["/help", "/cancel"]],
    resize_keyboard=True,
)


async def disconnect_client(context: ContextTypes.DEFAULT_TYPE) -> None:
    client = context.user_data.get("client")
    if client is not None:
        try:
            await client.disconnect()
        except Exception:
            pass
    context.user_data.clear()


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await disconnect_client(context)
    await update.message.reply_text(
        "Pyrogram Session String Generator\n\n"
        "I help you generate a Pyrogram v2 session string for your own "
        "Telegram account.\n\n"
        "Tap /generate to start.\n"
        "/help  - instructions and safety notes\n"
        "/cancel - abort current process\n\n"
        "WARNING: Never share your session string with anyone. Anyone "
        "who has it can fully control your account.",
        reply_markup=MAIN_KEYBOARD,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "How it works:\n\n"
        "1. Send /generate to start.\n"
        "2. Send your API ID (number from my.telegram.org).\n"
        "3. Send your API HASH.\n"
        "4. Send your phone number with country code (e.g. +8801XXXXXXXXX).\n"
        "5. Telegram will send a login code to your account. Send it back "
        "with SPACES between each digit (e.g. 1 2 3 4 5) so Telegram does "
        "not auto-revoke the code.\n"
        "6. If your account has 2-Step Verification enabled, the bot will "
        "ask for your password.\n"
        "7. The bot replies with your session string.\n\n"
        "Safety:\n"
        "- Use only a bot you trust (ideally your own deploy).\n"
        "- Never share the resulting session string.\n"
        "- If you suspect leakage, terminate the session from "
        "Telegram > Settings > Devices.",
        reply_markup=MAIN_KEYBOARD,
    )


async def generate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await disconnect_client(context)
    await update.message.reply_text(
        "Step 1 of 4\n\n"
        "Please send your API ID (a number).\n"
        "Get it from https://my.telegram.org\n\n"
        "Send /cancel to abort.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return API_ID


async def get_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        context.user_data["api_id"] = int(text)
    except ValueError:
        await update.message.reply_text(
            "API ID must be a number. Try again or /cancel."
        )
        return API_ID
    await update.message.reply_text(
        "Step 2 of 4\n\nNow send your API HASH."
    )
    return API_HASH


async def get_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["api_hash"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 3 of 4\n\n"
        "Send your phone number with country code.\n"
        "Example: +8801XXXXXXXXX"
    )
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip().replace(" ", "")
    client = Client(
        name=f"user_{update.effective_user.id}",
        api_id=context.user_data["api_id"],
        api_hash=context.user_data["api_hash"],
        in_memory=True,
    )

    try:
        await client.connect()
        sent = await client.send_code(phone)
    except ApiIdInvalid:
        try:
            await client.disconnect()
        except Exception:
            pass
        context.user_data.clear()
        await update.message.reply_text(
            "Invalid API ID / API HASH combination.\n"
            "Send /generate to start again.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END
    except PhoneNumberInvalid:
        try:
            await client.disconnect()
        except Exception:
            pass
        context.user_data.clear()
        await update.message.reply_text(
            "Invalid phone number.\nSend /generate to start again.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END
    except FloodWait as e:
        wait = getattr(e, "value", None) or getattr(e, "x", 0)
        try:
            await client.disconnect()
        except Exception:
            pass
        context.user_data.clear()
        await update.message.reply_text(
            f"Telegram says: flood wait {wait} seconds. Please try later.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END
    except Exception as e:
        logger.exception("send_code failed")
        try:
            await client.disconnect()
        except Exception:
            pass
        context.user_data.clear()
        await update.message.reply_text(
            f"Unexpected error: {e}\n\nSend /generate to start again.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    context.user_data["client"] = client
    context.user_data["phone"] = phone
    context.user_data["phone_code_hash"] = sent.phone_code_hash

    await update.message.reply_text(
        "Step 4 of 4\n\n"
        "An OTP has been sent to your Telegram app.\n\n"
        "Send the code with SPACES between each digit.\n"
        "Example: if the code is 12345, send  1 2 3 4 5\n\n"
        "(This avoids Telegram auto-revoking the code as soon as it is "
        "sent in plaintext.)"
    )
    return CODE


async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client: Client = context.user_data["client"]
    code = update.message.text.strip().replace(" ", "").replace("-", "")

    try:
        await client.sign_in(
            context.user_data["phone"],
            context.user_data["phone_code_hash"],
            code,
        )
    except PhoneCodeInvalid:
        await update.message.reply_text("Wrong code. Try again or /cancel.")
        return CODE
    except PhoneCodeExpired:
        await disconnect_client(context)
        await update.message.reply_text(
            "The code has expired. Send /generate to start again.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END
    except SessionPasswordNeeded:
        await update.message.reply_text(
            "Your account has 2-Step Verification enabled.\n\n"
            "Send your password, or /cancel to abort."
        )
        return PASSWORD
    except Exception as e:
        logger.exception("sign_in failed")
        await disconnect_client(context)
        await update.message.reply_text(
            f"Unexpected error: {e}\n\nSend /generate to start again.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    return await deliver_session(update, context)


async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client: Client = context.user_data["client"]
    try:
        await client.check_password(update.message.text)
    except PasswordHashInvalid:
        await update.message.reply_text("Wrong password. Try again or /cancel.")
        return PASSWORD
    except Exception as e:
        logger.exception("check_password failed")
        await disconnect_client(context)
        await update.message.reply_text(
            f"Unexpected error: {e}\n\nSend /generate to start again.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    return await deliver_session(update, context)


async def deliver_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client: Client = context.user_data["client"]
    try:
        session_string = await client.export_session_string()
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        context.user_data.clear()

    await update.message.reply_text(
        "Done! Here is your Pyrogram v2 session string.\n\n"
        "Keep it private. Anyone who has it can fully control your account."
    )
    # Send the string by itself in a code block so it is easy to copy
    await update.message.reply_text(
        f"`{session_string}`",
        parse_mode="Markdown",
    )
    await update.message.reply_text(
        "If you ever suspect this string has leaked, terminate the session "
        "from Telegram > Settings > Devices.\n\n"
        "Send /generate to create another session.",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await disconnect_client(context)
    await update.message.reply_text(
        "Cancelled. Send /generate to start a new session.",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("generate", generate_cmd)],
        states={
            API_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_api_id)],
            API_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_api_hash)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_cmd),
            CommandHandler("start", start_cmd),
            CommandHandler("help", help_cmd),
            CommandHandler("generate", generate_cmd),
        ],
        allow_reentry=True,
    )

    # Conversation handler must come BEFORE the standalone /start and /help
    # handlers so that /start while inside a conversation properly resets
    # the conversation state instead of being eaten by the global handler.
    application.add_handler(conv)
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))

    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
