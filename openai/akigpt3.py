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
    default_model: str = Field(default="flux")
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
    """Complete client with fixed image and text generation"""
    
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
        """Refresh available models from API"""
        global image_models, text_models
        try:
            async with self.session.get(f"{self.base_image_url}/models") as resp:
                image_models = await resp.json()
            async with self.session.get(f"{self.base_text_url}/models") as resp:
                text_models = await resp.json()
            logger.info("Updated model lists")
        except Exception as e:
            logger.error("Failed to refresh models: %s", e)
            image_models = ["flux", "stable-diffusion"]
            text_models = ["gpt-4o-mini", "mistral"]

    async def generate_image(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Fixed image generation with proper parameter handling"""
        try:
            # Build parameters with default values and validation
            params = {
                "model": kwargs.get("model", self.image_config.default_model),
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

            # URL-encode prompt and build URL
            encoded_prompt = aiohttp.helpers.quote(prompt)
            url = f"{self.base_image_url}/prompt/{encoded_prompt}"
            
            logger.debug("Image generation URL: %s", url)
            logger.debug("Image generation params: %s", params)

            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get('Content-Type', '')
                    if 'image/' in content_type:
                        image_data = await resp.read()
                        yield image_data
                    else:
                        text_response = await resp.text()
                        yield f"❌ Unexpected response: {text_response}"
                else:
                    error_text = await resp.text()
                    yield f"❌ Image generation failed ({resp.status}): {error_text}"

        except Exception as e:
            logger.error("Image generation error: %s", e, exc_info=True)
            yield "⚠️ Image service unavailable. Please try again later."

    async def chat_completion(self, messages: List[dict], **kwargs) -> AsyncGenerator[str, None]:
        """Async chat completion with proper error handling"""
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

    async def analyze_image(self, image_url: str, question: str) -> str:
        """Analyze images using vision capabilities"""
        try:
            payload = {
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }],
                "model": "gpt-4o-mini"
            }

            async with self.session.post(f"{self.base_text_url}/openai", json=payload) as resp:
                response = await resp.json()
                return response["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("Vision error: %s", e)
            return "⚠️ Failed to analyze image"

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
    """Fixed image command handler with proper media handling"""
    try:
        prompt = ' '.join(context.args)
        if not prompt:
            await update.message.reply_text("❌ Please provide a prompt after /imagine")
            return

        status_msg = await update.message.reply_text("🎨 Generating your image...")
        has_sent_image = False

        async for result in client.generate_image(prompt):
            if isinstance(result, bytes):
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=result,
                    reply_to_message_id=update.message.message_id
                )
                has_sent_image = True
                await status_msg.delete()
            elif isinstance(result, str):
                await status_msg.edit_text(result)
                if "❌" in result:
                    return

        if not has_sent_image:
            await status_msg.edit_text("⚠️ Failed to generate image - no data received")

    except Exception as e:
        logger.error("Image command error: %s", e, exc_info=True)
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

    logger.info("Starting AI chatbot with proper async management...")
    app.run_polling()

if __name__ == "__main__":
    main()