#!/usr/bin/env python3
# v2.0.0 - Enhanced AI Chat Bot
import os
import logging
import asyncio
import time
from typing import Dict, List, AsyncGenerator
from collections import defaultdict
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from openai import OpenAI

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variables
conversation_history: Dict[int, List[dict]] = {}
user_last_message: Dict[int, float] = defaultdict(float)
RATE_LIMIT_SECONDS = 1.0  # Minimum time between messages to prevent spam

class FreeLLMClient:
    """Enhanced Free LLM client with async streaming support and retry logic"""
    def __init__(self):
        self.client = OpenAI(
            base_url="https://text.pollinations.ai/openai",
            api_key="dummy-key"
        )
        self.model = "gpt-4"
        self.max_retries = 3
        self.retry_delay = 1.0

    async def stream_response(self, messages: List[dict]) -> AsyncGenerator[str, None]:
        """Async generator for LLM response chunks with retry logic"""
        for retry in range(self.max_retries):
            try:
                # Create a synchronous generator in a thread
                sync_gen = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    stream=True,
                    max_tokens=2000
                )
                loop = asyncio.get_event_loop()
                for chunk in await loop.run_in_executor(None, lambda: sync_gen):
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception as error:
                logger.error(f"LLM API error (retry {retry + 1}/{self.max_retries}): {error}")
                if retry < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (retry + 1))
                else:
                    yield "⚠️ Service temporarily unavailable. Please try again later."

# Initialize LLM client
llm_client = FreeLLMClient()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command to welcome the user"""
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text(
        "🤖 Welcome to the Enhanced AI Chat Bot!\n"
        "Type /help to see available commands.\n"
        "How can I assist you today?"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command to show available commands"""
    help_text = (
        "Available commands:\n"
        "/start - Start a new chat session\n"
        "/clear - Clear conversation history\n"
        "/help - Show this help message\n"
        "/stats - Show your chat statistics\n\n"
        "Feel free to ask me anything!"
    )
    await update.message.reply_text(help_text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the conversation history for the user"""
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🗑️ Conversation history cleared!")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user chat statistics"""
    user_id = update.effective_user.id
    messages = conversation_history.get(user_id, [])
    stats = (
        f"📊 Your Chat Statistics:\n"
        f"• Total messages: {len(messages)}\n"
        f"• User messages: {sum(1 for m in messages if m['role'] == 'user')}\n"
        f"• Bot responses: {sum(1 for m in messages if m['role'] == 'assistant')}\n"
    )
    await update.message.reply_text(stats)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages with rate limiting and streaming responses"""
    user_id = update.effective_user.id
    current_time = time.time()

    # Rate limiting
    if current_time - user_last_message[user_id] < RATE_LIMIT_SECONDS:
        await update.message.reply_text("⚠️ Please wait before sending another message.")
        return

    user_last_message[user_id] = current_time
    user_message = update.message.text

    # Initialize conversation history if not present
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # Append user message to conversation history
    conversation_history[user_id].append({"role": "user", "content": user_message})

    # Send a placeholder message while generating a response
    bot_message = await update.message.reply_text("🤔 Thinking...")

    try:
        full_response = ""
        async for chunk in llm_client.stream_response(conversation_history[user_id]):
            full_response += chunk
            try:
                await bot_message.edit_text(full_response)
            except Exception as e:
                logger.warning(f"Message edit error: {e}")

        # Append the bot's response to the conversation history
        conversation_history[user_id].append({"role": "assistant", "content": full_response})

    except Exception as error:
        logger.error(f"Error handling message: {error}")
        await bot_message.edit_text("❌ An error occurred. Please try again.")

def main() -> None:
    """Main function to initialize and run the bot"""
    try:
        bot_token = os.environ["TELEGRAM_TOKEN_KEY"]
    except KeyError:
        logger.critical("Missing TELEGRAM_TOKEN_KEY environment variable")
        return

    # Create the Telegram bot application
    app = Application.builder().token(bot_token).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the bot
    logger.info("Starting the bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
    
    