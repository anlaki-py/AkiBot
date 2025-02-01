#!/usr/bin/env python3
import os
import logging
import asyncio
from typing import Dict, List, AsyncGenerator
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

conversation_history: Dict[int, List[dict]] = {}

class FreeLLMClient:
    """Free LLM client with proper async streaming support"""
    def __init__(self):
        self.client = OpenAI(
            base_url="https://text.pollinations.ai/openai",
            api_key="dummy-key"
        )
        self.model = "gpt-4"
    
    async def stream_response(self, messages: List[dict]) -> AsyncGenerator[str, None]:
        """Async generator for LLM response chunks"""
        try:
            # Create sync generator in a thread
            sync_gen = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                stream=True
            )
            
            # Convert sync generator to async
            loop = asyncio.get_event_loop()
            for chunk in await loop.run_in_executor(None, lambda: sync_gen):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
        except Exception as error:
            logger.error("LLM API error: %s", error)
            yield "⚠️ Service temporarily unavailable. Please try again later."

# Initialize services
llm_client = FreeLLMClient()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text(
        "🤖 Welcome to Free AI Chat Bot!\n"
        "Type /help for commands"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Available commands:\n"
        "/start - New chat\n"
        "/clear - Reset history\n"
        "/help - Show this message"
    )
    await update.message.reply_text(help_text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("Conversation history cleared!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text
    
    try:
        if user_id not in conversation_history:
            conversation_history[user_id] = []
        
        conversation_history[user_id].append({"role": "user", "content": user_message})
        
        bot_message = await update.message.reply_text("...")
        full_response = ""
        
        async for chunk in llm_client.stream_response(conversation_history[user_id]):
            full_response += chunk
            try:
                await bot_message.edit_text(full_response)
            except Exception as e:
                logger.warning("Message edit error: %s", e)
        
        conversation_history[user_id].append({"role": "assistant", "content": full_response})
    
    except Exception as error:
        logger.error("Processing error: %s", error)
        await update.message.reply_text("Error processing request. Please try again.")

def main() -> None:
    try:
        bot_token = os.environ["TELEGRAM_TOKEN_KEY"]
    except KeyError:
        logger.critical("Missing TELEGRAM_TOKEN environment variable")
        return
    
    app = Application.builder().token(bot_token).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Starting bot...")
    app.run_polling()

if __name__ == "__main__":
    main()