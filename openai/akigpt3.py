#!/usr/bin/env python3
# v1.0.0
import os
import logging
import asyncio
import httpx
from urllib.parse import quote
from typing import Dict, List, AsyncGenerator, Optional
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

class ImageGenerationClient:
    """Client for handling image generation requests"""
    def __init__(self):
        self.base_url = "https://image.pollinations.ai/prompt"
        self.default_params = {
            "width": 1024,
            "height": 1024,
            "model": "stable-diffusion",  # Fallback model if flux is unavailable
            "seed": 42,
            "enhance": "true",
            "nologo": "false",
            "safe": "true"
        }
    
    async def generate_image(self, prompt: str, params: Optional[dict] = None) -> tuple[bool, bytes | str]:
        """Generate image from prompt"""
        try:
            # Merge default params with custom params
            request_params = self.default_params.copy()
            if params:
                request_params.update(params)
            
            # URL encode the prompt
            encoded_prompt = quote(prompt)
            url = f"{self.base_url}/{encoded_prompt}"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=request_params, timeout=30.0)
                
                if response.status_code == 200:
                    return True, response.content
                else:
                    error_data = response.json()
                    error_message = error_data.get('message', 'Unknown error')
                    if "No active flux servers" in error_message:
                        # Try with stable-diffusion model instead
                        request_params['model'] = 'stable-diffusion'
                        response = await client.get(url, params=request_params, timeout=30.0)
                        if response.status_code == 200:
                            return True, response.content
                    return False, f"Generation failed: {error_message}"
                    
        except Exception as e:
            logger.error(f"Image generation error: {e}")
            return False, "Failed to generate image. Please try again later."

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
            sync_gen = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                stream=True
            )
            
            loop = asyncio.get_event_loop()
            for chunk in await loop.run_in_executor(None, lambda: sync_gen):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
        except Exception as error:
            logger.error(f"LLM API error: {error}")
            yield "⚠️ Service temporarily unavailable. Please try again later."

# Initialize services
llm_client = FreeLLMClient()
image_client = ImageGenerationClient()

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
        "/image <prompt> - Generate image\n"
        "/help - Show this message"
    )
    await update.message.reply_text(help_text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("Conversation history cleared!")

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle image generation command"""
    if not context.args:
        await update.message.reply_text("Please provide a prompt after /image")
        return
    
    prompt = " ".join(context.args)
    status_message = await update.message.reply_text("🎨 Generating image...")
    
    try:
        success, result = await image_client.generate_image(prompt)
        if success:
            await update.message.reply_photo(
                photo=result,
                caption=f"🎨 Generated image for: {prompt}"
            )
            await status_message.delete()
        else:
            await status_message.edit_text(f"❌ {result}")
    
    except Exception as e:
        logger.error(f"Image command error: {e}")
        await status_message.edit_text("❌ Failed to generate image. Please try again later.")

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
                logger.warning(f"Message edit error: {e}")
        
        conversation_history[user_id].append({"role": "assistant", "content": full_response})
    
    except Exception as error:
        logger.error(f"Processing error: {error}")
        await update.message.reply_text("Error processing request. Please try again.")

def main() -> None:
    try:
        bot_token = os.environ["TELEGRAM_TOKEN_KEY"]
    except KeyError:
        logger.critical("Missing TELEGRAM_TOKEN environment variable")
        return
    
    app = Application.builder().token(bot_token).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("image", image_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Starting bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
