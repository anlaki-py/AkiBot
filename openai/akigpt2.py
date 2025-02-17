#!/usr/bin/env python3
import os
import json
import logging
import asyncio
from typing import Dict, List, Union, AsyncGenerator
from pydantic import BaseModel, Field
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
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

conversation_history: Dict[int, List[dict]] = {}

class ChatConfig(BaseModel):
    """Configuration model for chat parameters"""
    DEFAULT_MODEL: str = Field(default="gpt-4")
    MAX_TOKENS: int = Field(default=8192)
    TEMPERATURE: float = Field(default=0.7)
    TOP_P: float = Field(default=0.9)
    STOP_SEQUENCES: List[str] = Field(default=[])

class FreeLLMClient:
    """Enhanced LLM client with original pipe features"""
    
    class Valves(BaseModel):
        API_KEY: str = Field(default="dummy-key")
        BASE_URL: str = Field(default="https://text.pollinations.ai/openai")
    
    def __init__(self):
        self.valves = self.Valves(
            API_KEY=os.getenv("OPENAI_API_KEY", "dummy-key"),
            BASE_URL=os.getenv("OPENAI_BASE_URL", "https://text.pollinations.ai/openai")
        )
        self.config = ChatConfig()
        self.client = OpenAI(api_key=self.valves.API_KEY, base_url=self.valves.BASE_URL)
    
    def _process_message_content(self, message: dict) -> dict:
        """Process message content including multimedia"""
        if isinstance(message.get("content"), list):
            processed = []
            for content in message["content"]:
                if content["type"] == "text":
                    processed.append(content["text"])
                elif content["type"] == "image_url":
                    processed.append(f"[Image: {content['image_url']['url']}]")
            return {"role": message["role"], "content": " ".join(processed)}
        return message
    
    async def health_check(self) -> bool:
        """Check if the API endpoint is reachable"""
        try:
            response = self.client.chat.completions.create(
                model=self.config.DEFAULT_MODEL,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            return bool(response.choices[0].message.content)
        except Exception as e:
            if DEBUG:
                logger.error("Health check failed: %s", e)
            return False
    
    async def stream_response(self, messages: List[dict], params: dict) -> AsyncGenerator[str, None]:
        """Enhanced streaming response with configurable parameters"""
        try:
            processed_messages = [self._process_message_content(m) for m in messages]
            
            if DEBUG:
                logger.debug("API Request:\nModel: %s\nParams: %s\nMessages: %s",
                           self.config.DEFAULT_MODEL,
                           json.dumps(params, indent=2),
                           json.dumps(processed_messages, indent=2))

            sync_gen = self.client.chat.completions.create(
                model=self.config.DEFAULT_MODEL,
                messages=processed_messages,
                temperature=params.get("temperature", self.config.TEMPERATURE),
                top_p=params.get("top_p", self.config.TOP_P),
                max_tokens=params.get("max_tokens", self.config.MAX_TOKENS),
                stop=params.get("stop", self.config.STOP_SEQUENCES),
                stream=True
            )

            loop = asyncio.get_event_loop()
            for chunk in await loop.run_in_executor(None, lambda: sync_gen):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as error:
            logger.error("API Error: %s", error)
            yield "⚠️ Service unavailable. Please try again later."

# Initialize services
llm_client = FreeLLMClient()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initialize new chat session"""
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text(
        "🚀 AI Chat Bot Ready!\n"
        "/help for commands\n"
        "/clear to reset context"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information"""
    help_text = (
        "🤖 AI Chat Bot Help\n\n"
        "/start - Start new chat\n"
        "/clear - Reset conversation\n"
        "/help - Show this message\n\n"
        "Supports text and image URLs in messages!\n"
        f"Model: {llm_client.config.DEFAULT_MODEL}"
    )
    await update.message.reply_text(help_text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset conversation history"""
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🧹 Conversation history cleared!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process messages with enhanced capabilities"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    try:
        if not await llm_client.health_check():
            await update.message.reply_text("🔴 Service unavailable. Try again later.")
            return

        history = conversation_history.setdefault(user_id, [])
        history.append({"role": "user", "content": user_message})
        
        bot_message = await update.message.reply_text("...")
        full_response = ""
        
        async for chunk in llm_client.stream_response(
            messages=history,
            params={
                "temperature": 0.7,
                "max_tokens": 2048
            }
        ):
            full_response += chunk
            try:
                await bot_message.edit_text(full_response)
            except Exception as e:
                logger.warning("Message update error: %s", e)
        
        history.append({"role": "assistant", "content": full_response})

    except Exception as error:
        logger.error("Processing error: %s", error)
        await update.message.reply_text("Error processing request. Please try again.")

def main():
    """Main application setup"""
    try:
        bot_token = os.environ["TELEGRAM_TOKEN_KEY"]
    except KeyError:
        logger.critical("Missing TELEGRAM_TOKEN environment variable")
        return

    app = Application.builder().token(bot_token).build()
    
    # Register handlers
    handlers = [
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
        CommandHandler("clear", clear_command),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    ]
    
    for handler in handlers:
        app.add_handler(handler)

    logger.info("Starting enhanced AI chatbot...")
    app.run_polling()

if __name__ == "__main__":
    main()