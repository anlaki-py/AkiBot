#!/usr/bin/env python3
# v1.0.0
import os
import logging
import asyncio
import time
from typing import Dict, List, AsyncGenerator, Optional
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from openai import OpenAI

# Configure logging 
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Global Data Structures ---
conversation_history: Dict[int, List[dict]] = {}
user_last_message: Dict[int, float] = defaultdict(float)
RATE_LIMIT_SECONDS = 1.0  

# --- LLM Client ---
class FreeLLMClient:
    """LLM client with streaming, retries, and error handling."""

    def __init__(self):
        self.client = OpenAI(
            base_url="https://text.pollinations.ai/openai",
            api_key="dummy-key" 
        )
        self.model = "gpt-4"
        self.max_retries = 3
        self.retry_delay = 1.0

    async def generate_response(self, messages: List[dict], system_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Generates text responses from the LLM."""
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        for retry in range(self.max_retries):
            try:
                sync_gen = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    stream=True,
                    max_tokens=2000 
                )
                loop = asyncio.get_event_loop()
                async for chunk in self._process_chunks(sync_gen, loop):
                    yield chunk
                return 

            except Exception as error:
                logger.error(f"LLM API error (attempt {retry + 1}/{self.max_retries}): {error}")
                if retry < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (retry + 1))
                else:
                    yield "⚠️ Service is temporarily unavailable. Please try again later."

    async def _process_chunks(self, sync_gen, loop) -> AsyncGenerator[str, None]:
        """Processes text chunks from the LLM."""
        try:
            for chunk in await loop.run_in_executor(None, lambda: sync_gen):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Chunk processing error: {e}")
            yield "\n⚠️ Message processing was interrupted."

# Initialize the LLM client
llm_client = FreeLLMClient()

# --- Message Handling ---
class MessageManager:
    """Manages Telegram message formatting, splitting, and keyboards."""

    @staticmethod
    async def split_message(message: str, max_length: int = 4096) -> List[str]:
        """Splits long messages into Telegram-friendly chunks."""
        if len(message) <= max_length:
            return [message]

        chunks = []
        while message:
            if len(message) <= max_length:
                chunks.append(message)
                break
            split_index = message[:max_length].rfind('. ') + 1
            if split_index <= 0:
                split_index = max_length
            chunks.append(message[:split_index])
            message = message[split_index:].lstrip()
        return chunks

    @staticmethod
    def create_keyboard() -> InlineKeyboardMarkup:
        """Creates an inline keyboard for message actions."""
        keyboard = [
            [
                InlineKeyboardButton("🔄 Regenerate", callback_data="regenerate"),
                InlineKeyboardButton("❌ Delete", callback_data="delete")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

# --- Telegram Bot Commands ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command, welcoming the user."""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    conversation_history[user_id] = []
    welcome_message = (
        f"👋 Welcome {user_name}! I'm your AI assistant. How can I help you today?"
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command, providing information about the bot."""
    help_text = (
        "🤖 *Commands*\n\n"
        "🔹 /start - Start a new chat\n"
        "🔹 /clear - Clear conversation history\n"
        "🔹 /help - Show this help message\n"
        "🔹 /stats - Show your chat statistics\n\n"
        "*Features*:\n"
        "• Remembers our conversation\n"
        "• Regenerate responses\n"
        "• Protected against spamming\n"
        "• Handles errors gracefully\n\n"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /clear command, resetting the conversation history."""
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🗑 Conversation history cleared!")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /stats command, showing user chat statistics."""
    user_id = update.effective_user.id
    messages = conversation_history.get(user_id, [])
    stats = (
        "📊 *Your Chat Statistics*\n\n"
        f"• Total messages: {len(messages)}\n"
        f"• Your messages: {sum(1 for m in messages if m['role'] == 'user')}\n"
        f"• My responses: {sum(1 for m in messages if m['role'] == 'assistant')}\n"
    )
    await update.message.reply_text(stats, parse_mode='Markdown')

# --- Callback Handling ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline keyboard button presses."""
    query = update.callback_query
    await query.answer() 
    if query.data == "delete":
        await query.message.delete()
    elif query.data == "regenerate":
        user_id = query.from_user.id
        if user_id in conversation_history and conversation_history[user_id]:
            if len(conversation_history[user_id]) >= 2:
                conversation_history[user_id] = conversation_history[user_id][:-2] 
            await handle_message(update, context, is_regeneration=True)

# --- Core Message Handling Logic ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, is_regeneration: bool = False) -> None:
    """Handles incoming text messages from the user."""
    user_id = update.effective_user.id
    current_time = time.time()

    # Rate Limiting
    if not is_regeneration and current_time - user_last_message[user_id] < RATE_LIMIT_SECONDS:
        await update.message.reply_text("⚠️ Please wait a moment before sending another message.")
        return

    user_last_message[user_id] = current_time
    user_message = update.message.text if not is_regeneration else conversation_history[user_id][-1]['content']

    try:
        if user_id not in conversation_history:
        