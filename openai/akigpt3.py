#!/usr/bin/env python3
import os
import logging
import asyncio
import aiohttp
import json
from typing import Dict, List, AsyncGenerator
from pydantic import BaseModel, Field
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Global storage
conversation_history: Dict[int, List[dict]] = {}
image_models = []
text_models = []

class ImageConfig(BaseModel):
    """Configuration for image generation"""
    default_model: str = Field(default="stable-diffusion")
    default_width: int = Field(default=1024)
    default_height: int = Field(default=1024)
    max_size: int = Field(default=2048)
    enhance_prompts: bool = Field(default=True)

class TextConfig(BaseModel):
    """Configuration for text generation"""
    default_model: str = Field(default="gpt-4o-mini")
    max_tokens: int = Field(default=4096)
    temperature: float = Field(default=0.7)

class PollinationsClient:
    """Improved client with working image generation and model handling"""
    
    def __init__(self):
        self.image_config = ImageConfig()
        self.text_config = TextConfig()
        self.base_image_url = "https://image.pollinations.ai"
        self.base_text_url = "https://text.pollinations.ai"
        self.session = None

    async def aenter(self):
        """Initialize async resources"""
        self.session = aiohttp.ClientSession()
        await self.refresh_models()
        return self

    async def aclose(self):
        """Cleanup async resources"""
        if self.session:
            await self.session.close()

    async def refresh_models(self):
        """Refresh available models with proper parsing"""
        global image_models, text_models
        try:
            async with self.session.get(f"{self.base_image_url}/models") as resp:
                image_data = await resp.json()
                image_models = [m["id"] for m in image_data if "id" in m]
            
            async with self.session.get(f"{self.base_text_url}/models") as resp:
                text_data = await resp.json()
                text_models = [m["id"] for m in text_data if "id" in m]
            
            logger.info("Updated model lists")
            logger.debug("Image models: %s", image_models)
            logger.debug("Text models: %s", text_models)

        except Exception as e:
            logger.error("Failed to refresh models: %s", e)
            image_models = ["stable-diffusion", "kandinsky"]
            text_models = ["gpt-4o-mini", "mistral"]

    async def generate_image(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Robust image generation with model fallback"""
        try:
            # Try with default model first
            yield await self._generate_image_with_model(
                prompt,
                self.image_config.default_model,
                **kwargs
            )
        except Exception as e:
            logger.warning("Failed with default model, trying alternatives: %s", e)
            for model in image_models:
                if model != self.image_config.default_model:
                    try:
                        yield await self._generate_image_with_model(prompt, model, **kwargs)
                        break
                    except Exception as fallback_error:
                        logger.warning("Failed with model %s: %s", model, fallback_error)
            else:
                yield "⚠️ All image generation services are currently unavailable"

    async def _generate_image_with_model(self, prompt: str, model: str, **kwargs) -> bytes:
        """Internal image generation with specific model"""
        params = {
            "model": model,
            "width": str(min(
                kwargs.get("width", self.image_config.default_width),
                self.image_config.max_size
            )),
            "height": str(min(
                kwargs.get("height", self.image_config.default_height),
                self.image_config.max_size
            )),
            "seed": str(kwargs.get("seed", "")),
            "nologo": str(kwargs.get("nologo", False)).lower(),
            "enhance": str(kwargs.get("enhance", self.image_config.enhance_prompts)).lower(),
            "safe": str(kwargs.get("safe", True)).lower()
        }

        # Remove empty parameters
        params = {k: v for k, v in params.items() if v and v not in ['none', '']}

        encoded_prompt = aiohttp.helpers.quote(prompt)
        url = f"{self.base_image_url}/prompt/{encoded_prompt}"
        
        logger.info("Generating image with model: %s", model)
        async with self.session.get(url, params=params) as resp:
            if resp.status == 200:
                content_type = resp.headers.get('Content-Type', '')
                if 'image/' in content_type:
                    return await resp.read()
                raise Exception(f"Unexpected content type: {content_type}")
            raise Exception(f"API Error {resp.status}: {await resp.text()}")

    async def chat_completion(self, messages: List[dict], **kwargs) -> AsyncGenerator[str, None]:
        """Reliable chat completion implementation"""
        try:
            url = f"{self.base_text_url}/openai"
            payload = {
                "messages": messages,
                "model": kwargs.get("model", self.text_config.default_model),
                "temperature": kwargs.get("temperature", self.text_config.temperature),
                "max_tokens": kwargs.get("max_tokens", self.text_config.max_tokens),
                "stream": True
            }

            async with self.session.post(url, json=payload) as resp:
                async for line in resp.content:
                    if line.startswith(b'data: '):
                        try:
                            data = json.loads(line[6:])
                            if content := data["choices"][0]["delta"].get("content"):
                                yield content
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            logger.error("Chat error: %s", e)
            yield "⚠️ Chat service unavailable. Please try again later."

# Initialize client
client = PollinationsClient()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initialize new chat session"""
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text(
        "🚀 AI Chat Bot Ready!\n"
        "Available commands:\n"
        "/help - Show commands\n"
        "/imagine - Generate images\n"
        "/models - List available models\n"
        "/clear - Reset conversation"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information"""
    help_text = (
        "🤖 AI Chat Bot Help\n\n"
        "/start - Start new chat\n"
        "/imagine [prompt] - Generate image\n"
        "/models [image|text] - List models\n"
        "/clear - Reset conversation\n"
        "/help - Show this message\n\n"
        "Supports text, images, and vision analysis!"
    )
    await update.message.reply_text(help_text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset conversation history"""
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🧹 Conversation history cleared!")

async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /models command with proper error handling"""
    try:
        model_type = context.args[0].lower() if context.args else "all"
        
        response = "🛠️ Available Models:\n"
        if model_type in ["image", "all"]:
            response += "\n📸 Image Models:\n- " + "\n- ".join(image_models)
        if model_type in ["text", "all"]:
            response += "\n📝 Text Models:\n- " + "\n- ".join(text_models)
        
        await update.message.reply_text(response)
    except Exception as e:
        logger.error("Models command error: %s", e)
        await update.message.reply_text("⚠️ Models not loaded yet. Try again in a moment.")

async def imagine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Robust image command handler with multiple fallbacks"""
    try:
        prompt = ' '.join(context.args)
        if not prompt:
            await update.message.reply_text("❌ Please provide a prompt after /imagine")
            return

        status_msg = await update.message.reply_text("🎨 Generating your image...")
        attempts = 0

        async for result in client.generate_image(prompt):
            if isinstance(result, bytes):
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=result,
                    reply_to_message_id=update.message.message_id
                )
                await status_msg.delete()
                return
            elif isinstance(result, str):
                await status_msg.edit_text(result)
                if "unavailable" in result:
                    return

        await status_msg.edit_text("⚠️ Failed to generate image after multiple attempts")

    except Exception as e:
        logger.error("Image command error: %s", e)
        await update.message.reply_text("⚠️ Failed to generate image")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all messages with text and image support"""
    user_id = update.effective_user.id
    message = update.message

    try:
        if message.photo:
            image_file = await message.photo[-1].get_file()
            response = await client.analyze_image(
                image_file.file_path, 
                message.caption or "Describe this image"
            )
            await message.reply_text(response)
            return

        history = conversation_history.setdefault(user_id, [])
        history.append({"role": "user", "content": message.text})
        
        bot_msg = await message.reply_text("💭 Thinking...")
        full_response = ""
        
        async for chunk in client.chat_completion(history):
            full_response += chunk
            try:
                await bot_msg.edit_text(full_response)
            except:
                pass
        
        history.append({"role": "assistant", "content": full_response})

    except Exception as e:
        logger.error("Message handling error: %s", e)
        await message.reply_text("⚠️ Error processing request")

async def setup_client(app: Application):
    """Initialize client when application starts"""
    await client.aenter()
    app.job_queue.run_repeating(client.refresh_models, interval=3600)

async def shutdown_client(app: Application):
    """Cleanup client when application stops"""
    await client.aclose()

def main():
    """Main application setup with proper async management"""
    try:
        bot_token = os.environ["TELEGRAM_TOKEN_KEY"]
    except KeyError:
        logger.critical("Missing TELEGRAM_TOKEN environment variable")
        return

    # Create application with lifecycle handlers
    app = Application.builder().token(bot_token).post_init(setup_client).post_shutdown(shutdown_client).build()
    
    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("models", list_models))
    app.add_handler(CommandHandler("imagine", imagine_command))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    logger.info("Starting improved AI chatbot...")
    app.run_polling()

if __name__ == "__main__":
    main()