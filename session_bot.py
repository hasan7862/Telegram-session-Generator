"""
Telegram Session String Generator + Checker Bot

Features:
- /generate — create a new Pyrogram v2 / Telethon session string
- /check    — verify if a session string is still active
              (user provides own API ID / HASH + session string)
- /status   — show total unique users
"""

# ============================================================================
# CONFIG
# ============================================================================

import os

BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    "8770901362:AAE0VcqO2YM6qnA_d8RqUmWnSbC2O3AAwAc",
)
PORT = int(os.environ.get("PORT", "8080"))

# ============================================================================
# Compatibility shim for Python 3.12+
# ============================================================================

import asyncio

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# ============================================================================
# Tiny HTTP server for Render health check
# ============================================================================

from threading import Thread
from flask import Flask

flask_app = Flask(__name__)


@flask_app.route("/")
def root():
    return "Telegram session bot is running."


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

from pyrogram import Client as PyroClient
from pyrogram.errors import (
    ApiIdInvalid as PyroApiIdInvalid,
    AuthKeyUnregistered as PyroAuthKeyUnregistered,
    UserDeactivated as PyroUserDeactivated,
    UserDeactivatedBan as PyroUserDeactivatedBan,
    FloodWait as PyroFloodWait,
    PasswordHashInvalid as PyroPasswordHashInvalid,
    PhoneCodeExpired as PyroPhoneCodeExpired,
    PhoneCodeInvalid as PyroPhoneCodeInvalid,
    PhoneNumberInvalid as PyroPhoneNumberInvalid,
    SessionPasswordNeeded as PyroSessionPasswordNeeded,
)

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    ApiIdInvalidError as TeleApiIdInvalid,
    AuthKeyUnregisteredError as TeleAuthKeyUnregistered,
    UserDeactivatedError as TeleUserDeactivated,
    UserDeactivatedBanError as TeleUserDeactivatedBan,
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

# Conversation states for /generate
CHOICE, API_ID, API_HASH, PHONE, CODE, PASSWORD = range(6)
# Conversation states for /check (user provides API id/hash + session)
CHECK_API_ID, CHECK_API_HASH, CHECK_SESSION = range(100, 103)

# Track every unique user (resets on restart — Render free tier has no disk)
all_users = set()


def track_user(update: Update) -> None:
    try:
        u = update.effective_user
        if u and not u.is_bot:
            all_users.add(u.id)
    except Exception:
        pass


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["/generate", "/check"], ["/status", "/help"], ["/cancel"]],
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


# ============================================================================
# /start, /help, /status, /cancel
# ============================================================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
    await disconnect_client(context)
    await update.message.reply_text(
        "Telegram Session String Bot\n\n"
        "What I can do:\n"
        "• /generate — create a new Pyrogram or Telethon session string\n"
        "• /check    — check whether a session string is still valid\n"
        "• /status   — bot status & total users\n"
        "• /help     — full instructions\n"
        "• /cancel   — abort current step\n\n"
        "WARNING: Never share your session string with anyone. Anyone "
        "who has it can fully control your account.",
        reply_markup=MAIN_KEYBOARD,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
    await update.message.reply_text(
        "GENERATE a session:\n"
        "1. /generate → choose 1 (Pyrogram) or 2 (Telethon)\n"
        "2. Send API ID, API HASH (from my.telegram.org)\n"
        "3. Send phone with country code (e.g. +8801XXXXXXXXX)\n"
        "4. Send the OTP with SPACES (e.g. 1 2 3 4 5)\n"
        "5. If 2FA is on, send your password\n"
        "6. You receive your session string\n\n"
        "CHECK a session:\n"
        "1. /check\n"
        "2. Send your API ID\n"
        "3. Send your API HASH\n"
        "4. Paste the session string (Pyrogram or Telethon — auto-detect)\n"
        "5. Bot tells you whether it is still ACTIVE or DEAD\n\n"
        "STATUS:\n"
        "• /status shows the bot is alive and the total user count\n\n"
        "Safety: Never share session strings with strangers. If leaked, "
        "terminate from Telegram > Settings > Devices.",
        reply_markup=MAIN_KEYBOARD,
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
    await update.message.reply_text(
        "📊 Bot Status\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"✅ Bot: online\n"
        f"👥 Total users: {len(all_users)}\n"
        f"🛠 Generator: ready\n"
        f"🔍 Checker: ready\n"
        f"💰 Cost: free\n"
        "━━━━━━━━━━━━━━━━━━",
        reply_markup=MAIN_KEYBOARD,
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
    await disconnect_client(context)
    await update.message.reply_text(
        "Cancelled. Send /generate or /check to start again.",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ============================================================================
# /generate flow
# ============================================================================

async def generate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
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
    await update.message.reply_text("Step 3 of 5\n\nNow send your API HASH.")
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

    client = None
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
        else:
            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            sent = await client.send_code_request(phone)
            context.user_data["phone_code_hash"] = sent.phone_code_hash
    except (PyroApiIdInvalid, TeleApiIdInvalid):
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        context.user_data.clear()
        await update.message.reply_text(
            "Invalid API ID / API HASH combination.\nSend /generate to start again.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END
    except (PyroPhoneNumberInvalid, TelePhoneNumberInvalid):
        if client:
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
        if client:
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
        if client:
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
        "(This avoids Telegram auto-revoking the code.)"
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
        else:
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
        else:
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
        else:
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
    await update.message.reply_text(
        f"`{session_string}`",
        parse_mode="Markdown",
    )
    await update.message.reply_text(
        "If you ever suspect this string has leaked, terminate the session "
        "from Telegram > Settings > Devices.\n\n"
        "Send /generate to create another, or /check to verify a session.",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ============================================================================
# /check flow — Session Validity Checker
# ============================================================================

async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
    await disconnect_client(context)
    await update.message.reply_text(
        "🔍 Session Checker — Step 1 of 3\n\n"
        "Send your API ID (a number).\n"
        "Get it from https://my.telegram.org\n\n"
        "Send /cancel to abort.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CHECK_API_ID


async def check_get_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        context.user_data["check_api_id"] = int(text)
    except ValueError:
        await update.message.reply_text(
            "API ID must be a number. Try again or /cancel."
        )
        return CHECK_API_ID
    await update.message.reply_text(
        "🔍 Session Checker — Step 2 of 3\n\nNow send your API HASH."
    )
    return CHECK_API_HASH


async def check_get_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["check_api_hash"] = update.message.text.strip()
    await update.message.reply_text(
        "🔍 Session Checker — Step 3 of 3\n\n"
        "Now paste your session string (Pyrogram or Telethon — auto-detect).\n\n"
        "For your safety, I will delete the message after reading it."
    )
    return CHECK_SESSION


async def _try_pyrogram(api_id: int, api_hash: str, session_str: str):
    """Returns (ok, info_or_error_str). ok: True=alive, False=dead, None=parse error."""
    client = None
    try:
        client = PyroClient(
            name="checker_pyro",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_str,
            in_memory=True,
            no_updates=True,
        )
        await client.connect()
        me = await client.get_me()
        info = {
            "library": "Pyrogram v2",
            "id": me.id,
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
            "username": me.username or "",
            "phone": me.phone_number or "",
            "is_premium": getattr(me, "is_premium", False),
        }
        return True, info
    except (PyroAuthKeyUnregistered, PyroUserDeactivated, PyroUserDeactivatedBan) as e:
        return False, f"dead: {type(e).__name__}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass


async def _try_telethon(api_id: int, api_hash: str, session_str: str):
    """Returns (ok, info_or_error_str). ok: True=alive, False=dead, None=parse error."""
    client = None
    try:
        client = TelegramClient(
            StringSession(session_str),
            api_id,
            api_hash,
        )
        await client.connect()
        if not await client.is_user_authorized():
            return False, "dead: not authorized"
        me = await client.get_me()
        info = {
            "library": "Telethon",
            "id": me.id,
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
            "username": me.username or "",
            "phone": me.phone or "",
            "is_premium": getattr(me, "premium", False),
        }
        return True, info
    except (TeleAuthKeyUnregistered, TeleUserDeactivated, TeleUserDeactivatedBan) as e:
        return False, f"dead: {type(e).__name__}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass


async def check_get_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_str = update.message.text.strip()
    api_id = context.user_data.get("check_api_id")
    api_hash = context.user_data.get("check_api_hash")

    if not api_id or not api_hash:
        context.user_data.clear()
        await update.message.reply_text(
            "Missing API ID / HASH. Send /check to start again.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    if len(session_str) < 30:
        await update.message.reply_text(
            "That doesn't look like a session string. Paste the full string or /cancel."
        )
        return CHECK_SESSION

    # Delete the user's message so the session string is not left in chat
    try:
        await update.message.delete()
    except Exception:
        pass

    status_msg = await update.effective_chat.send_message(
        "⏳ Checking session... please wait."
    )

    # Try Pyrogram first, then Telethon. Auto-detect.
    ok_pyro, result_pyro = await _try_pyrogram(api_id, api_hash, session_str)
    if ok_pyro is True:
        ok, result = True, result_pyro
    elif ok_pyro is False:
        ok, result = False, result_pyro
    else:
        ok_tele, result_tele = await _try_telethon(api_id, api_hash, session_str)
        if ok_tele is True:
            ok, result = True, result_tele
        elif ok_tele is False:
            ok, result = False, result_tele
        else:
            ok, result = None, f"Pyrogram error: {result_pyro}\nTelethon error: {result_tele}"

    # Wipe sensitive data from memory
    context.user_data.clear()

    try:
        await status_msg.delete()
    except Exception:
        pass

    if ok is True:
        info = result
        full_name = f"{info['first_name']} {info['last_name']}".strip()
        username = f"@{info['username']}" if info['username'] else "—"
        phone = info['phone'] or "—"
        if phone != "—" and not phone.startswith("+"):
            phone = "+" + phone
        premium = "Yes" if info['is_premium'] else "No"

        await update.effective_chat.send_message(
            "✅ Session is ACTIVE\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📚 Format: {info['library']}\n"
            f"👤 Name: {full_name or '—'}\n"
            f"🆔 User ID: {info['id']}\n"
            f"🔗 Username: {username}\n"
            f"📱 Phone: {phone}\n"
            f"⭐ Premium: {premium}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Your session string was deleted from this chat for safety.",
            reply_markup=MAIN_KEYBOARD,
        )
    elif ok is False:
        await update.effective_chat.send_message(
            "❌ Session is DEAD\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "This session string is no longer valid. Possible reasons:\n"
            "• Logged out from Telegram > Devices\n"
            "• Account banned or deactivated\n"
            "• Session was revoked\n\n"
            f"Detail: {result}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Use /generate to create a new session.",
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        await update.effective_chat.send_message(
            "⚠️ Couldn't verify the session\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "The string didn't match Pyrogram or Telethon format, or "
            "Telegram returned an unexpected error. Common causes:\n"
            "• Wrong API ID / HASH\n"
            "• Session string copied incompletely\n"
            "• Extra spaces or line breaks in the string\n\n"
            f"Detail:\n{result}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Send /check to try again.",
            reply_markup=MAIN_KEYBOARD,
        )

    return ConversationHandler.END


# ============================================================================
# Main
# ============================================================================

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    generate_conv = ConversationHandler(
        entry_points=[CommandHandler("generate", generate_cmd)],
        states={
            CHOICE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_choice)],
            API_ID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_api_id)],
            API_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_api_hash)],
            PHONE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            CODE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_cmd),
            CommandHandler("start", start_cmd),
            CommandHandler("help", help_cmd),
            CommandHandler("status", status_cmd),
            CommandHandler("generate", generate_cmd),
            CommandHandler("check", check_cmd),
        ],
        allow_reentry=True,
    )

    check_conv = ConversationHandler(
        entry_points=[CommandHandler("check", check_cmd)],
        states={
            CHECK_API_ID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, check_get_api_id)],
            CHECK_API_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_get_api_hash)],
            CHECK_SESSION:  [MessageHandler(filters.TEXT & ~filters.COMMAND, check_get_session)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_cmd),
            CommandHandler("start", start_cmd),
            CommandHandler("help", help_cmd),
            CommandHandler("status", status_cmd),
            CommandHandler("generate", generate_cmd),
            CommandHandler("check", check_cmd),
        ],
        allow_reentry=True,
    )

    application.add_handler(generate_conv)
    application.add_handler(check_conv)
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("status", status_cmd))

    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
