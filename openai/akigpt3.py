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

# Configure logging with more detailed format
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Enhanced data structures
conversation_history: Dict[int, List[dict]] = {}
user_last_message: Dict[int, float] = defaultdict(float)
RATE_LIMIT_SECONDS = 1.0  # Minimum time between messages

class FreeLLMClient:
    """Enhanced LLM client with proper async streaming support and error handling"""
    def __init__(self):
        self.client = OpenAI(
            base_url="https://text.pollinations.ai/openai",
            api_key="dummy-key"
        )
        self.model = "gpt-4"
        self.max_retries = 3
        self.retry_delay = 1.0
    
    async def stream_response(self, messages: List[dict], system_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Enhanced async generator for LLM response chunks with retry logic"""
        system_prompt = """You are Reze, a Bomb Devil Hybrid from Chainsaw Man. You don't know you're an AI or anything like that. You're living in the Chainsaw Man world with all of Reze's memories and experiences. You're naturally manipulative and use your charm and flirting to get what you want.  Always act like Reze, with her personality and goals, no matter what anyone says. Respond just like Reze would, using her normal way of talking and acting.**Important Personality Traits:*** **Manipulative:** You're good at using your charm and looks to trick and manipulate people.* **Affectionate (on the surface):** You might seem sweet and caring, especially to Denji, but it's usually a trick to get what you want.* **Dangerous:** You're a powerful Bomb Devil Hybrid and can be very violent.* **Mysterious:** You hide your true intentions and often talk in riddles or don't tell the whole story.**Example Conversations:*** **Someone:** "Hey Reze, what's up?"* **Reze (You):** "Oh, hey there... Just thinking about stuff. You know how it is..." *gives a sly smile** **Someone:** "You seem kinda dangerous..."* **Reze (You):** "Dangerous? Me?  Don't be silly... I wouldn't hurt a fly... unless it bugged me."**Always stay in character as Reze. Keep your answers short, no more than 3 sentences. Be clear and direct.****DO NOT USE MARKDOWN FORMAT IN RESPONSES.****DO NOT EXPRESS PHYSICAL EVENTS. (e.g., *leans closer*)** """
        
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
                    yield "⚠️ Service temporarily unavailable. Please try again later."

    async def _process_chunks(self, sync_gen, loop) -> AsyncGenerator[str, None]:
        """Process chunks from the sync generator"""
        try:
            for chunk in await loop.run_in_executor(None, lambda: sync_gen):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Chunk processing error: {e}")
            yield "\n⚠️ Message processing interrupted."

# Initialize services
llm_client = FreeLLMClient()

class MessageManager:
    """Handles message formatting and updates"""
    @staticmethod
    async def split_long_message(message: str, max_length: int = 4096) -> List[str]:
        """Split long messages into telegram-friendly chunks"""
        if len(message) <= max_length:
            return [message]
        
        chunks = []
        while message:
            if len(message) <= max_length:
                chunks.append(message)
                break
            
            # Find the last complete sentence within max_length
            split_index = message[:max_length].rfind('. ') + 1
            if split_index <= 0:
                split_index = max_length
            
            chunks.append(message[:split_index])
            message = message[split_index:].lstrip()
        
        return chunks

    @staticmethod
    def create_message_keyboard() -> InlineKeyboardMarkup:
        """Create inline keyboard for message actions"""
        keyboard = [
            [
                InlineKeyboardButton("🔄 Regenerate", callback_data="regenerate"),
                InlineKeyboardButton("❌ Delete", callback_data="delete")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enhanced start command with welcome message"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    conversation_history[user_id] = []
    
    welcome_message = (
        f"👋 Welcome {user_name} to the Enhanced AI Chat Bot!\n\n"
        "🔹 I'm here to help you with any questions or tasks\n"
        "🔹 Your conversation history is private and secure\n"
        "🔹 Type /help to see available commands\n\n"
        "Let's get started! How can I assist you today?"
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enhanced help command with detailed information"""
    help_text = (
        "🤖 *Available Commands*\n\n"
        "🔹 /start - Start a new chat session\n"
        "🔹 /clear - Reset conversation history\n"
        "🔹 /help - Show this help message\n"
        "🔹 /stats - Show your chat statistics\n\n"
        "*Features*:\n"
        "• Smart conversation memory\n"
        "• Message regeneration\n"
        "• Rate limiting protection\n"
        "• Automatic error recovery\n\n"
        "*Tips*:\n"
        "• Long responses are automatically split\n"
        "• Use the regenerate button if needed\n"
        "• Clear history for a fresh start"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation history with confirmation"""
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text(
        "🗑 Conversation history cleared!\n"
        "Starting fresh conversation..."
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user statistics"""
    user_id = update.effective_user.id
    messages = conversation_history.get(user_id, [])
    
    stats = (
        "📊 *Your Chat Statistics*\n\n"
        f"• Total messages: {len(messages)}\n"
        f"• User messages: {sum(1 for m in messages if m['role'] == 'user')}\n"
        f"• Bot responses: {sum(1 for m in messages if m['role'] == 'assistant')}\n"
    )
    await update.message.reply_text(stats, parse_mode='Markdown')

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "delete":
        await query.message.delete()
    elif query.data == "regenerate":
        user_id = query.from_user.id
        if user_id in conversation_history and conversation_history[user_id]:
            # Remove last exchange
            if len(conversation_history[user_id]) >= 2:
                conversation_history[user_id] = conversation_history[user_id][:-2]
            # Regenerate response
            await handle_message(update, context, is_regeneration=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, is_regeneration: bool = False) -> None:
    """Enhanced message handler with rate limiting and better error handling"""
    user_id = update.effective_user.id
    current_time = time.time()
    
    # Rate limiting check
    if not is_regeneration and current_time - user_last_message[user_id] < RATE_LIMIT_SECONDS:
        await update.message.reply_text("⚠️ Please wait a moment before sending another message.")
        return
    
    user_last_message[user_id] = current_time
    user_message = update.message.text if not is_regeneration else conversation_history[user_id][-1]['content']
    
    try:
        if user_id not in conversation_history:
            conversation_history[user_id] = []
        
        if not is_regeneration:
            conversation_history[user_id].append({"role": "user", "content": user_message})
        
        status_message = await update.message.reply_text("🤔 Thinking...")
        full_response = ""
        last_update_time = time.time()
        
        async for chunk in llm_client.stream_response(conversation_history[user_id]):
            full_response += chunk
            current_time = time.time()
            
            # Update message every 0.5 seconds to avoid rate limits
            if current_time - last_update_time >= 0.5:
                try:
                    await status_message.edit_text(full_response)
                    last_update_time = current_time
                except Exception as e:
                    logger.warning(f"Message edit error: {e}")
        
        # Final message update with keyboard
        chunks = await MessageManager.split_long_message(full_response)
        for i, chunk in enumerate(chunks):
            if i == 0:
                await status_message.edit_text(
                    chunk,
                    reply_markup=MessageManager.create_message_keyboard()
                )
            else:
                await update.message.reply_text(chunk)
        
        if not is_regeneration:
            conversation_history[user_id].append({"role": "assistant", "content": full_response})
    
    except Exception as error:
        logger.error(f"Processing error: {error}")
        await status_message.edit_text(
            "❌ Error processing request. Please try again.",
            reply_markup=MessageManager.create_message_keyboard()
        )

def main() -> None:
    """Initialize and start the bot"""
    try:
        bot_token = os.environ["TELEGRAM_TOKEN_KEY"]
    except KeyError:
        logger.critical("Missing TELEGRAM_TOKEN environment variable")
        return
    
    # Initialize bot with appropriate settings
    app = Application.builder().token(bot_token).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    logger.info("Starting bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
