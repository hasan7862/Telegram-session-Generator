"""
Telegram Session String Generator Bot

Supports BOTH Pyrogram v2 AND Telethon session strings.
The bot owner only needs a BOT_TOKEN.
End users provide their OWN API_ID, API_HASH, phone, login code, and
2-Step Verification password (if any) inside the chat with the bot.
"""

# ============================================================================
# CONFIG
# ============================================================================

BOT_TOKEN = "8770901362:AAE0VcqO2YM6qnA_d8RqUmWnSbC2O3AAwAc"

import os
PORT = int(os.environ.get("PORT", "8080"))

# ============================================================================
# Compatibility shim: Python 3.12+ removed the implicit event loop in the
# main thread. Pyrogram 2.0.106's sync wrapper calls asyncio.get_event_loop()
# at import time. Create a loop explicitly BEFORE importing pyrogram.
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
# Imports
# ============================================================================

import logging

# Pyrogram imports
from pyrogram import Client as PyroClient
from pyrogram.errors import (
    ApiIdInvalid as PyroApiIdInvalid,
    FloodWait as PyroFloodWait,
    PasswordHashInvalid as PyroPasswordHashInvalid,
    PhoneCodeExpired as PyroPhoneCodeExpired,
    PhoneCodeInvalid as PyroPhoneCodeInvalid,
    PhoneNumberInvalid as PyroPhoneNumberInvalid,
    SessionPasswordNeeded as PyroSessionPasswordNeeded,
)

# Telethon imports
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    ApiIdInvalidError as TeleApiIdInvalid,
    FloodWaitError as TeleFloodWait,
    PasswordHashInvalidError as TelePasswordHashInvalid,
    PhoneCodeExpiredError as TelePhoneCodeExpired,
    PhoneCodeInvalidError as TelePhoneCodeInvalid,
    PhoneNumberInvalidError as TelePhoneNumberInvalid,
    SessionPasswordNeededError as TeleSessionPasswordNeeded,
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
logging.getLogger("telethon").setLevel(logging.WARNING)
logger = logging.getLogger("session-bot")

# Conversation states
CHOICE, API_ID, API_HASH, PHONE, CODE, PASSWORD = range(6)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["/generate"], ["/help", "/cancel"]],
    resize_keyboard=True,
)

CHOICE_KEYBOARD = ReplyKeyboardMarkup(
    [["1 - Pyrogram", "2 - Telethon"], ["/cancel"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


# ============================================================================
# Helpers
# ============================================================================

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
        "Telegram Session String Generator\n\n"
        "I help you generate a session string for your own Telegram account.\n"
        "You can choose between Pyrogram v2 and Telethon formats.\n\n"
        "Tap /generate to start.\n"
        "/help   - instructions and safety notes\n"
        "/cancel - abort current process\n\n"
        "WARNING: Never share your session string with anyone. Anyone "
        "who has it can fully control your account.",
        reply_markup=MAIN_KEYBOARD,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "How it works:\n\n"
        "1. Send /generate to start.\n"
        "2. Choose the library: 1 (Pyrogram) or 2 (Telethon).\n"
        "3. Send your API ID (number from my.telegram.org).\n"
        "4. Send your API HASH.\n"
        "5. Send your phone number with country code (e.g. +8801XXXXXXXXX).\n"
        "6. Telegram will send a login code to your account. Send it back "
        "with SPACES between each digit (e.g. 1 2 3 4 5) so Telegram does "
        "not auto-revoke the code.\n"
        "7. If your account has 2-Step Verification enabled, the bot will "
        "ask for your password.\n"
        "8. The bot replies with your session string.\n\n"
        "Pyrogram vs Telethon:\n"
        "- Use Pyrogram if your downstream code uses pyrogram.Client.\n"
        "- Use Telethon if your downstream code uses telethon.TelegramClient.\n"
        "- The two formats are NOT interchangeable.\n\n"
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
        "Step 1 of 5\n\n"
        "Which library do you want the session string for?\n\n"
        "Send  1  for Pyrogram v2\n"
        "Send  2  for Telethon\n\n"
        "Send /cancel to abort.",
        reply_markup=CHOICE_KEYBOARD,
    )
    return CHOICE


async def get_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    # Accept "1", "2", "1 - pyrogram", "2 - telethon", "pyrogram", "telethon"
    if text.startswith("1") or "pyro" in text:
        context.user_data["library"] = "pyrogram"
        lib_name = "Pyrogram v2"
    elif text.startswith("2") or "tele" in text:
        context.user_data["library"] = "telethon"
        lib_name = "Telethon"
    else:
        await update.message.reply_text(
            "Please send 1 (Pyrogram) or 2 (Telethon).",
            reply_markup=CHOICE_KEYBOARD,
        )
        return CHOICE

    await update.message.reply_text(
        f"Selected: {lib_name}\n\n"
        "Step 2 of 5\n\n"
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
        "Step 3 of 5\n\nNow send your API HASH."
    )
    return API_HASH


async def get_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["api_hash"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 4 of 5\n\n"
        "Send your phone number with country code.\n"
        "Example: +8801XXXXXXXXX"
    )
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip().replace(" ", "")
    library = context.user_data.get("library", "pyrogram")
    api_id = context.user_data["api_id"]
    api_hash = context.user_data["api_hash"]

    try:
        if library == "pyrogram":
            client = PyroClient(
                name=f"user_{update.effective_user.id}",
                api_id=api_id,
                api_hash=api_hash,
                in_memory=True,
            )
            await client.connect()
            sent = await client.send_code(phone)
            context.user_data["phone_code_hash"] = sent.phone_code_hash
        else:  # telethon
            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            sent = await client.send_code_request(phone)
            context.user_data["phone_code_hash"] = sent.phone_code_hash
    except (PyroApiIdInvalid, TeleApiIdInvalid):
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
    except (PyroPhoneNumberInvalid, TelePhoneNumberInvalid):
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
    except (PyroFloodWait, TeleFloodWait) as e:
        wait = getattr(e, "value", None) or getattr(e, "seconds", None) or getattr(e, "x", 0)
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

    await update.message.reply_text(
        "Step 5 of 5\n\n"
        "An OTP has been sent to your Telegram app.\n\n"
        "Send the code with SPACES between each digit.\n"
        "Example: if the code is 12345, send  1 2 3 4 5\n\n"
        "(This avoids Telegram auto-revoking the code as soon as it is "
        "sent in plaintext.)"
    )
    return CODE


async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = context.user_data["client"]
    library = context.user_data.get("library", "pyrogram")
    code = update.message.text.strip().replace(" ", "").replace("-", "")

    try:
        if library == "pyrogram":
            await client.sign_in(
                context.user_data["phone"],
                context.user_data["phone_code_hash"],
                code,
            )
        else:  # telethon
            await client.sign_in(
                phone=context.user_data["phone"],
                code=code,
                phone_code_hash=context.user_data["phone_code_hash"],
            )
    except (PyroPhoneCodeInvalid, TelePhoneCodeInvalid):
        await update.message.reply_text("Wrong code. Try again or /cancel.")
        return CODE
    except (PyroPhoneCodeExpired, TelePhoneCodeExpired):
        await disconnect_client(context)
        await update.message.reply_text(
            "The code has expired. Send /generate to start again.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END
    except (PyroSessionPasswordNeeded, TeleSessionPasswordNeeded):
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
    client = context.user_data["client"]
    library = context.user_data.get("library", "pyrogram")
    pw = update.message.text

    try:
        if library == "pyrogram":
            await client.check_password(pw)
        else:  # telethon
            await client.sign_in(password=pw)
    except (PyroPasswordHashInvalid, TelePasswordHashInvalid):
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
    client = context.user_data["client"]
    library = context.user_data.get("library", "pyrogram")
    try:
        if library == "pyrogram":
            session_string = await client.export_session_string()
            label = "Pyrogram v2"
        else:  # telethon
            session_string = client.session.save()
            label = "Telethon"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        context.user_data.clear()

    await update.message.reply_text(
        f"Done! Here is your {label} session string.\n\n"
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
            CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_choice)],
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

    application.add_handler(conv)
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))

    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
