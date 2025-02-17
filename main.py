# main.py v1.4.7
import os
import io
import json
import tempfile
import uuid
import asyncio
from typing import Optional, Union, Callable, Any
from functools import wraps
import pickle
import base64
import requests
import re
import telegram
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram import Update, Message, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.error import TimedOut, NetworkError, RetryAfter
from PIL import Image
import io
import urllib.parse
import shutil
from pathlib import Path
from datetime import datetime
from utils.tools.akibot_tools import print_akibot_logo as logo, clear_screen
from utils.flask.config_editor import config_editor
from utils.commands.insta.insta import InstagramDownloader
from utils.commands.ytb2mp3.ytb2mp3 import YouTubeDownloader
from utils.commands.web2md.web2md import WebToMarkdownConverter
from utils.commands.start.start import start_command
from utils.commands.help.help import help_command
from utils.commands.clear.clear import clear_command
from utils.commands.think.think import think_command
from utils.commands.ytb2transcript.ytb2transcript import handler as transcript_handler
from utils.commands.jailbreak.jailbreak import jailbreak_command, jailbreak_callback_handler

class Config:
    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = config_path
        self._last_modified = 0
        self._config_cache = {}
        
    def _load_config(self) -> None:
        """Load configuration if file has been modified."""
        current_mtime = os.path.getmtime(self.config_path)
        if current_mtime > self._last_modified:
            with open(self.config_path, "r") as f:
                self._config_cache = json.load(f)
            with open(self._config_cache["system_prompt_file"], "r") as f:
                self._config_cache["system_instructions"] = f.read()
            self._last_modified = current_mtime

    def _get_config_value(self, key: str) -> Any:
        """Get a config value, reloading if necessary."""
        self._load_config()
        return self._config_cache[key]

    telegram_token = os.getenv("TELEGRAM_TOKEN_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    @property
    def allowed_users(self) -> list:
        return self._get_config_value("allowed_users")

    @property
    def model_name(self) -> str:
        return self._get_config_value("gemini_model")

    @property
    def generation_config(self) -> dict:
        return self._get_config_value("generation_config")

    @property
    def safety_settings(self) -> dict:
        return self._get_config_value("safety_settings")

    @property
    def system_instructions(self) -> str:
        return self._get_config_value("system_instructions")
        
class Chat:

    def __init__(self, history=None):
        self.history = history if history else []

    async def send_message_async(self, content, role="user"):
        if isinstance(content, str):
            content = [{"text": content}]

        message = {
            "role": "user",
            "parts": content if isinstance(content, list) else [content]
        }
        self.history.append(message)
        # return await self.get_response()
        if role == "user":
            return await self.get_response()
        return None

    async def get_response(self):
        return Response(self.history[-1])  # Latest message

class Response:

    def __init__(self, text):
        self.text = text["parts"][0]["text"] if isinstance(
            text["parts"][0], dict) else text["parts"][0]

class AIBot:
    MAX_RETRIES = 3
    RETRY_DELAY = 3  # seconds
    USER_DATA_ROOT = "data/users"
    GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    INSTAGRAM_URL_REGEX = re.compile(
        r'(?:https?://)?(?:www\.)?instagram\.com/(?:p/|reel/)([\w-]+)')

    def __init__(self):
        self.config = Config()
        self.chat_history = {}
        self.instagram_downloader = InstagramDownloader(
        )  # Instantiate the InstagramDownloader
        self.youtube_downloader = YouTubeDownloader()
        self.YOUTUBE_URL_REGEX = re.compile(
            r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)'
        )
        self.web2md_converter = WebToMarkdownConverter()

        # No need to configure genai library anymore
        self.api_url = f"{self.GEMINI_API_URL}/{self.config.model_name}"
        self.headers = {"Content-Type": "application/json"}

        self.allowed_extensions = {
            ".txt", ".xml", ".py", ".js", ".html", ".css", ".ps1", ".json",
            ".md", ".yaml", ".yml", ".ts", ".tsx", ".c", ".cpp", ".h", ".hpp",
            ".java", ".cs", ".php", ".pl", ".rb", ".sh", ".bat", ".ini",
            ".log", ".toml", ".rs", ".go", ".r", ".jl", ".lua", ".swift",
            ".sql", ".asm", ".vb", ".vbs", ".jsx", ".svelte", ".vue", ".scss",
            ".less", ".tex", ".rmd", ".m", ".scala", ".erl", ".hs", ".f90",
            ".pas", ".groovy"
        }

    def get_user_dir(self, user_id: str, username: str) -> str:
        """Get base directory for user data."""
        sanitized_username = (username.replace(" ", "_").replace("/", "-") 
                             if username else "unknown")
        return os.path.join(
            self.USER_DATA_ROOT,
            f"{sanitized_username}_{user_id}"
        )    

    def get_history_file_path(self, user_id: str, username: str) -> str:
        """Generate history file path in user-specific directory."""
        sanitized_username = (username.replace(" ", "_").replace("/", "-") 
                            if username else "unknown")
        user_dir = os.path.join(
            self.USER_DATA_ROOT,
            f"{sanitized_username}_{user_id}"
        )
        history_dir = os.path.join(user_dir, "history")
        os.makedirs(history_dir, exist_ok=True)
        return os.path.join(history_dir, "chat_history.pkl")

    async def load_chat_history(self, user_id: str, username: str) -> Optional[list]:
        """Load chat history from new directory structure."""
        file_path = self.get_history_file_path(user_id, username)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"Error loading history: {e}")
        return None

    async def generate_content(self, contents, stream=False):
        endpoint = "streamGenerateContent" if stream else "generateContent"
        url = f"{self.api_url}:{endpoint}?{'alt=sse&' if stream else ''}key={self.config.gemini_api_key}"       
        payload = {
            "contents":
            contents,
            "safetySettings": [{
                "category": k,
                "threshold": v
            } for k, v in self.config.safety_settings.items()],
            "generationConfig":
            self.config.generation_config
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            if stream:
                # Handle streaming response
                return response.iter_lines()
            else:
                return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error making request to Gemini API: {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}")
            raise

    async def handle_gemini_response(self, response):
        """Handle Gemini API response and extract text content."""
        try:
            if not response.get("candidates"):
                error = response.get("error", {})
                if error:
                    raise Exception(f"API Error: {error.get('message', 'Unknown error')}")
                raise Exception("No response candidates returned")
                
            text_response = response["candidates"][0]["content"]["parts"][0].get("text")
            if not text_response:
                raise Exception("No text content in response")
                
            return text_response
            
        except Exception as e:
            print(f"Error handling Gemini response: {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}")
            raise

    async def retry_operation(self, operation: Callable, *args,
                              **kwargs) -> Any:
        """Retry an operation with exponential backoff."""
        for attempt in range(self.MAX_RETRIES):
            try:
                return await operation(*args, **kwargs)
            except (TimedOut, NetworkError) as e:
                if attempt == self.MAX_RETRIES - 1:
                    raise
                delay = self.RETRY_DELAY * (2**attempt)
                print(
                    f"Operation failed with {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}, retrying in {delay} seconds..."
                )
                await asyncio.sleep(delay)
            except RetryAfter as e:
                print(f"Rate limited, waiting {e.retry_after} seconds...")
                await asyncio.sleep(e.retry_after)
                return await operation(*args, **kwargs)

    def check_user_access(func: Callable) -> Callable:
        """Decorator to check user access permissions."""

        @wraps(func)
        async def wrapper(self, update: Update,
                          context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = str(update.effective_user.id)
            if user_id not in self.config.allowed_users:
                await self.retry_operation(
                    update.message.reply_text,
                    f"Access Denied: You do not have permission to use this bot.\n"
                    f"Please contact the [developer](https://t.me/<USERNAME>) of this bot to request access.\n"
                    f"Your ID: `{user_id}`",
                    parse_mode='Markdown')
                return
            return await func(self, update, context, *args, **kwargs)

        return wrapper

    def global_user_access(func: Callable) -> Callable:
        """Decorator to check user access permissions."""

        @wraps(func)
        async def wrapper(self, update: Update,
                          context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = str(update.effective_user.id)
            if user_id not in []:
                await self.retry_operation(
                    update.message.reply_text,
                    f"Access Denied: This feature is currently undergoing maintenance. We expect it to be fully operational shortly. Thank you for your patience. 🛠️\n",
                    parse_mode='Markdown')
                return
            return await func(self, update, context, *args, **kwargs)

        return wrapper

    # New helper method for info files
    def get_info_file_path(self, user_id: str, username: str, filename: str) -> str:
        """Get path for user info files."""
        user_dir = self.get_user_dir(user_id, username)
        info_dir = os.path.join(user_dir, "info")
        os.makedirs(info_dir, exist_ok=True)
        return os.path.join(info_dir, filename)

    async def load_chat_history(self, user_id: str,
                                username: str) -> Optional[list]:
        """Load chat history from a pickle file if it exists."""
        file_path = self.get_history_file_path(user_id, username)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as f:
                    history_data = pickle.load(f)
                    return history_data
            except Exception as e:
                print(f"Error loading chat history from {file_path}: {e}")
                return None
        return None

    async def save_chat_history(self, user_id: str, username: str) -> None:
        """Save chat history to user-specific directory."""
        file_path = self.get_history_file_path(user_id, username)
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as f:
                pickle.dump(self.chat_history[user_id].history, f)
        except Exception as e:
            print(f"Error saving chat history: {e}")
            
    async def initialize_chat(self, user_id: str, username: str) -> None:
        """Initialize chat history for a user if not exists."""
        if user_id not in self.chat_history:
            loaded_history = await self.load_chat_history(user_id, username)
            if loaded_history:
                self.chat_history[user_id] = Chat(history=loaded_history)
            else:
                self.chat_history[user_id] = Chat(history=[])
                await self.retry_operation(
                    self.chat_history[user_id].send_message_async,
                    self.config.system_instructions,
                    role="system")

    async def process_file(self, message: Message, process_func: Callable) -> Optional[str]:
        """Generic file processing with cleanup and retry logic."""
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                await self.retry_operation(process_func, temp_file.name)
                return await self.handle_processed_file(temp_file.name, message)
        except Exception as e:
            return f"An error occurred: {str(e).replace(self.config.gemini_api_key, '[REDACTED TOKEN]')}"
        finally:
            if temp_file and os.path.exists(temp_file.name):
                os.remove(temp_file.name)
    
    async def handle_processed_file(self, file_path: str, message: Message) -> str:
        """Handle the processed file and get AI response with retry logic."""
        user_id = str(message.from_user.id)
        username = str(message.from_user.username)
        caption = message.caption or "user: [No caption provided]"
    
        try:
            if message.photo:
                with Image.open(file_path) as img:
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG')
                    img_b64 = base64.b64encode(buf.getvalue()).decode()
                    content = [{
                        "text": f"user: {caption}"
                    }, {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": img_b64
                        }
                    }]
            elif message.document:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = [{
                        "text": f"user: {caption}"
                    }, {
                        "text": f.read()
                    }]
            elif message.audio or message.voice:
                audio_msg = message.audio or message.voice
                with open(file_path, "rb") as f:
                    audio_b64 = base64.b64encode(f.read()).decode()
                    
                    # Include audio metadata
                    duration = audio_msg.duration
                    file_size = audio_msg.file_size
                    mime_type = "audio/ogg"
                    if message.audio:
                        mime_type = message.audio.mime_type or mime_type
                        
                    content = [{
                        "text": f"user: Audio message - Duration: {duration}s, Size: {file_size} bytes\nCaption: {caption}"
                    }, {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": audio_b64
                        }
                    }]
            else:
                return "Unsupported file type"
    
            # Get the chat history for the user
            chat = self.chat_history[user_id]
            await chat.send_message_async(content, role="user")
    
            response = await self.generate_content(chat.history)
            text_response = await self.handle_gemini_response(response)
            
            await chat.send_message_async(f"{text_response}", role="assistant")
            await self.save_chat_history(user_id, username)
            return text_response
        except Exception as e:
            return f"Error processing file: {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}"

# = Instagram Downloader =============================================================================================================

    async def handle_instagram_command(self,
                                       update: Update,
                                       context: ContextTypes.DEFAULT_TYPE,
                                       as_file: bool = False) -> None:
        """
        Generic handler for Instagram media downloads.

        Args:
            update: Telegram update object
            context: Telegram context object
            as_file: Whether to send media as uncompressed files
        """
        await self.instagram_downloader.handle_instagram_command(
            self, update, context, as_file)

    # Command handlers
    @check_user_access
    async def insta_command(self, update: Update,
                            context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /insta command to download Instagram media as compressed media."""
        await self.handle_instagram_command(update, context, as_file=False)

    @check_user_access
    async def insta_file_command(self, update: Update,
                                 context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /instaFile command to download Instagram media as uncompressed files."""
        await self.handle_instagram_command(update, context, as_file=True)

# = YouTube Downloader =============================================================================================================

    @check_user_access
    async def ytb2mp3_command(self, update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /ytb2mp3 command to download YouTube videos as MP3."""
        await self.youtube_downloader.handle_youtube_command(
            self, update, context)

# = Web-page to Markdown =============================================================================================================

    @check_user_access
    async def web2md_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /web2md command to convert webpages to Markdown."""
        await self.web2md_converter.handle_web2md_command(self, update, context)
# = Thinking Command ============================================================================================================

    @check_user_access
    async def think_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /think command with detailed reasoning"""
        await think_command.handle_think_command(self, update, context)

# = YouTube Transcript Command ============================================================================================================

    @check_user_access
    async def ytb2transcript_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /ytb2transcript command"""
        await transcript_handler.handle_ytb2transcript_command(self, update, context)

# = Jailbreak Command =============================================================================================================

    @check_user_access
    async def jailbreak_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await jailbreak_command(self, update, context)

    async def jailbreak_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await jailbreak_callback_handler(self, update, context)
                    
# = Basic Commands ============================================================================================================

    # @check_user_access
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await start_command(self, update, context)

    @check_user_access
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await help_command(self, update, context)

    @check_user_access
    async def clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await clear_command(self, update, context)

# ==============================================================================================================

    async def get_replied_message_content(self, message: Message) -> Optional[dict]:
        """
        Extract content and metadata from the replied-to message.
        Returns None if this is a new message (not a reply).

        Args:
            message: The Telegram message object

        Returns:
            Optional[dict]: Message content and metadata if it's a reply, None otherwise
        """
        if not message.reply_to_message:
            return None

        replied_msg = message.reply_to_message
        result = {
            'content': None,
            'role': 'assistant' if replied_msg.from_user.is_bot else 'user',
            'type': 'unknown'
        }

        try:
            if replied_msg.text:
                result['content'] = replied_msg.text
                result['type'] = 'text'
            elif replied_msg.photo:
                file_obj = await self.retry_operation(replied_msg.photo[-1].get_file)
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                    await file_obj.download_to_drive(temp_file.name)
                    try:
                        with Image.open(temp_file.name) as img:
                            buf = io.BytesIO()
                            img.save(buf, format='JPEG')
                            img_b64 = base64.b64encode(buf.getvalue()).decode()
                            result['content'] = [{  # Enclose in a list for consistency
                                "text": "[Image]",
                                "image_data": img_b64,
                                "caption": replied_msg.caption or ""
                            }]
                            result['type'] = 'image'
                    finally:
                        os.unlink(temp_file.name)
            elif replied_msg.document:
                if replied_msg.document.file_name.endswith(tuple(self.allowed_extensions)):
                    file_obj = await self.retry_operation(replied_msg.document.get_file)
                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                        await file_obj.download_to_drive(temp_file.name)
                        try:
                            with open(temp_file.name, 'r', encoding='utf-8') as f:
                                result['content'] = f.read()
                                result['type'] = 'document'
                        finally:
                            os.unlink(temp_file.name)
                else:
                    result['content'] = "[Unsupported Document]"
                    result['type'] = 'unsupported_document'
            elif replied_msg.voice or replied_msg.audio:
                result['content'] = "[Audio message]"  # or handle audio data if needed
                result['type'] = 'audio'
            # Add more elif blocks for other message types as required (video, sticker, etc.)

        except Exception as e:
            print(f"Error processing replied message: {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}")
            result['content'] = "[Error processing previous message]"
            result['type'] = 'error'

        return result

    def format_reply_context(self, reply_info: dict, current_message: str) -> Union[str, list]:
        """Format the reply context with metadata about the replied message."""

        role_label = "AI assistant" if reply_info['role'] == "assistant" else "user"

        if reply_info['type'] == 'image':
            try:
                image_content = reply_info['content'][0]  # Access the first element which is the image dictionary
                return [  # Construct list-based structure
                    {
                        "text": (
                            f"CONTEXT: Replying to an image from {role_label}.\n"
                            f"CAPTION: {image_content.get('caption', '[No caption]')}\n"
                            f"IMAGE: [Image data below]\n\n"  # Indicate image placement
                            f"NEW MESSAGE:\n{current_message}"
                        )
                    },
                    {  # Include image data
                       "inline_data": {
                            "mime_type": "image/jpeg",  # Assuming JPEG, adjust if needed
                            "data": image_content['image_data']
                        }
                    }
                ]
            except (IndexError, KeyError) as e: # Handle potential errors
                print(f"Error formatting image reply context: {e}")
                return f"Error processing image reply.  New message:\n{current_message}"

        elif reply_info['type'] == 'document':
            return (
                f"CONTEXT: Replying to a document from {role_label}.\n"
                f"DOCUMENT CONTENT:\n{reply_info['content']}\n\n"
                f"NEW MESSAGE:\n{current_message}"
            )
        elif reply_info['type'] == 'unsupported_document':
            return (
                f"CONTEXT: Replying to an unsupported document from {role_label}.\n\n"
                f"NEW MESSAGE:\n{current_message}"
            )

        elif reply_info['type'] in ('audio', 'voice'):  # Handle other types as needed
            return (
                f"CONTEXT: Replying to an audio message from {role_label}.\n\n"
                f"NEW MESSAGE:\n{current_message}"
            )        
        else: # Default for text or other simple messages
            return (
                f"CONTEXT: Replying to a message from {role_label}:\n"
                f"{reply_info['content']}\n\n"
                f"NEW MESSAGE:\n{current_message}"
            )
       
    async def send_response_with_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                         text: str, reply_to_message_id: int = None, 
                                         reply_markup: InlineKeyboardMarkup = None) -> None:
        try:
            # Initialize message cache if not exists
            if 'message_cache' not in context.chat_data:
                context.chat_data['message_cache'] = {}
                
            # Determine the correct message and reply method based on update type
            if update.callback_query:
                # For callback queries
                message = update.callback_query.message
                reply_method = message.edit_text
                chat_id = message.chat_id
            else:
                # For regular messages
                message = update.message
                reply_method = message.reply_text
                chat_id = message.chat_id
            
            # Generate unique callback data if not using a custom reply markup
            if not reply_markup:
                callback_data = f"toggle_md_{uuid.uuid4()}"
                
                # Create keyboard with toggle button
                reply_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("Render Markdown", callback_data=callback_data)
                ]])
            else:
                # If a custom reply_markup is provided, use a placeholder callback data
                callback_data = f"toggle_md_{uuid.uuid4()}"
            
            sent_messages = []
            
            # Handle messages longer than 4096 characters
            if len(text) > 4096:
                chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
                
                for i, chunk in enumerate(chunks):
                    chunk_markup = None
                    if i == len(chunks) - 1:  # Only add button to last chunk
                        chunk_markup = reply_markup
                    
                    if update.callback_query:
                        # For callback queries, edit existing message
                        sent_msg = await self.retry_operation(
                            context.bot.edit_message_text,
                            chat_id=chat_id,
                            message_id=message.message_id,
                            text=chunk,
                            reply_markup=chunk_markup
                        )
                    else:
                        # For regular messages, reply
                        sent_msg = await self.retry_operation(
                            reply_method,
                            chunk,
                            reply_to_message_id=reply_to_message_id if i == 0 else None,
                            reply_markup=chunk_markup
                        )
                    sent_messages.append(sent_msg)
            else:
                if update.callback_query:
                    # For callback queries, edit existing message
                    sent_msg = await self.retry_operation(
                        context.bot.edit_message_text,
                        chat_id=chat_id,
                        message_id=message.message_id,
                        text=text,
                        reply_markup=reply_markup
                    )
                else:
                    # For regular messages, reply
                    sent_msg = await self.retry_operation(
                        reply_method,
                        text,
                        reply_to_message_id=reply_to_message_id,
                        reply_markup=reply_markup
                    )
                sent_messages.append(sent_msg)
            
            # Store message data in context
            context.chat_data['message_cache'][callback_data] = {
                'text': text,
                'messages': [msg.message_id for msg in sent_messages],
                'markdown_mode': False
            }
            
            return sent_messages
            
        except Exception as e:
            # Fallback error handling for both message types
            try:
                error_message = f"Error sending message: {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}"
                if update.callback_query:
                    await update.callback_query.message.reply_text(error_message)
                else:
                    await update.message.reply_text(error_message)
            except Exception as fallback_error:
                print(f"Critical error in send_response_with_toggle: {fallback_error}")
            return None
            
    @check_user_access    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
        user_id = str(update.effective_user.id)
        username = str(update.effective_user.username)
        await self.initialize_chat(user_id, username)
    
        text = update.message.text
        
        if 'transcript_state' in context.chat_data:
            await transcript_handler.process_transcript_steps(self, update, context)
            return        
        
        try:
            chat = self.chat_history[user_id]
            
            try:
                reply_info = await self.get_replied_message_content(update.message)
            except ValueError as ve:
                await self.send_response_with_toggle(update, context, "Cannot reply to voice or audio messages")
                return
                
            if reply_info:
                formatted_context = self.format_reply_context(reply_info, text)
                await chat.send_message_async(formatted_context, role="user")
            else:
                await chat.send_message_async(f"user: {text}", role="user")
            
            response = await self.retry_operation(
                self.generate_content,
                chat.history,
                stream=False
            )
            
            text_response = await self.handle_gemini_response(response)                        
            await chat.send_message_async(f"{text_response}", role="assistant")
            await self.save_chat_history(user_id, username)
            
            # Use the new utility method to send the response
            await self.send_response_with_toggle(update, context, text_response)
                
        except Exception as e:
            error_message = f"An error occurred: {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}"
            await self.send_response_with_toggle(update, context, error_message)

    @check_user_access    
    async def handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
        user_id = str(update.effective_user.id)
        username = str(update.effective_user.username)
        await self.initialize_chat(user_id, username)
    
        try:
            if not (update.message.voice or update.message.audio):
                reply_info = await self.get_replied_message_content(update.message)
                
                if reply_info:
                    formatted_context = self.format_reply_context(
                        reply_info,
                        update.message.caption or "[No caption]"
                    )
                    
                    if isinstance(formatted_context, list):
                        await self.chat_history[user_id].send_message_async(formatted_context, role="user")
                    else:
                        await self.chat_history[user_id].send_message_async(formatted_context, role="user")
    
            # Handle different media types
            if update.message.voice or update.message.audio:
                file_obj = await self.retry_operation((update.message.voice or update.message.audio).get_file)
                result = await self.process_file(update.message, lambda path: file_obj.download_to_drive(path))
            elif update.message.photo:
                file_obj = await self.retry_operation(update.message.photo[-1].get_file)
                result = await self.process_file(update.message, lambda path: file_obj.download_to_drive(path))
            elif update.message.document:
                file_extension = os.path.splitext(update.message.document.file_name)[1].lower()
                if file_extension not in self.allowed_extensions:
                    await self.send_response_with_toggle(update, context, "Unsupported document type.")
                    return
                file_obj = await self.retry_operation(update.message.document.get_file)
                result = await self.process_file(update.message, lambda path: file_obj.download_to_drive(path))
            else:
                result = "Unsupported media type"
    
            # Use the new utility method to send the response
            await self.send_response_with_toggle(update, context, result)
                
        except Exception as e:
            error_message = f"Error handling media: {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}"
            await self.send_response_with_toggle(update, context, error_message)
    
    async def toggle_markdown_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the Markdown toggle button callback."""
        query = update.callback_query
        await query.answer()
        
        try:
            # Get cached message data
            cache_key = query.data
            if 'message_cache' not in context.chat_data or cache_key not in context.chat_data['message_cache']:
                await query.edit_message_reply_markup(
                    InlineKeyboardMarkup([[
                        InlineKeyboardButton("Message expired", callback_data="expired")
                    ]])
                )
                return
    
            message_data = context.chat_data['message_cache'][cache_key]
            current_mode = message_data['markdown_mode']
            text = message_data['text']
            message_ids = message_data['messages']
    
            # Toggle Markdown mode
            new_mode = not current_mode
            button_text = "Show Plain Text" if new_mode else "Render Markdown"
            
            # Prepare new keyboard
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(button_text, callback_data=cache_key)
            ]])
    
            # Update all messages in the chain
            chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
            for i, (chunk, msg_id) in enumerate(zip(chunks, message_ids)):
                try:                    
                    if new_mode:
                        await context.bot.edit_message_text(
                            chat_id=query.message.chat_id,
                            message_id=msg_id,
                            text=chunk,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=keyboard if i == len(message_ids) - 1 else None
                        )
                    else:
                        await context.bot.edit_message_text(
                            chat_id=query.message.chat_id,
                            message_id=msg_id,
                            text=chunk,
                            reply_markup=keyboard if i == len(message_ids) - 1 else None
                        )
                except telegram.error.BadRequest as e:
                    if "can't parse entities" in str(e).lower():
                        # Markdown parsing failed, revert to plain text
                        await context.bot.edit_message_text(
                            chat_id=query.message.chat_id,
                            message_id=msg_id,
                            text=f"⚠️ Markdown rendering failed. Some syntax might be invalid:\n\n{chunk}",
                            reply_markup=keyboard if i == len(message_ids) - 1 else None
                        )
                    else:
                        raise
    
            # Update cache
            message_data['markdown_mode'] = new_mode
            context.chat_data['message_cache'][cache_key] = message_data
    
        except Exception as e:
            try:
                await query.edit_message_reply_markup(
                    InlineKeyboardMarkup([[
                        InlineKeyboardButton("Error occurred", callback_data="error")
                    ]])
                )
            except:
                pass
            print(f"Error in toggle_markdown_callback: {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}")                

    async def count_tokens(self, contents):
        """Count tokens in the content to manage context window."""
        url = f"{self.api_url}:countTokens?key={self.config.gemini_api_key}"
        
        try:
            response = requests.post(url, headers=self.headers, json={"contents": contents})
            response.raise_for_status()
            return response.json().get("totalTokens", 0)
        except Exception as e:
            print(f"Error counting tokens: {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}")
            return 0

    async def manage_chat_history(self, user_id: str, max_tokens: int = 500000):
        """Manage chat history to prevent token limit issues."""
        if user_id in self.chat_history:
            history = self.chat_history[user_id].history
            total_tokens = await self.count_tokens(history)
            
            while total_tokens > max_tokens and len(history) > 1:
                # Remove oldest messages while preserving system instruction
                if len(history) > 1:
                    history.pop(1)  # Keep system instruction at index 0
                total_tokens = await self.count_tokens(history)
    
    def run(self) -> None:
        """Start the bot with error handling."""
        try:
            application = (
                Application.builder().token(
                    self.config.telegram_token).get_updates_read_timeout(30).
                get_updates_write_timeout(30).get_updates_connect_timeout(30).
                get_updates_pool_timeout(30).read_timeout(30).write_timeout(
                    30).connect_timeout(30).pool_timeout(30).build())

            # Register handlers
            application.add_handler(CommandHandler("start", self.start))
            application.add_handler(CommandHandler("help", self.help_command))
            application.add_handler(CommandHandler("clear", self.clear))
            application.add_handler(CommandHandler("insta", self.insta_command))
            application.add_handler(CommandHandler("instaFile", self.insta_file_command))
            application.add_handler(CommandHandler("ytb2mp3", self.ytb2mp3_command))
            application.add_handler(CommandHandler("web2md", self.web2md_command))
            application.add_handler(CommandHandler("think", self.think_command))
            application.add_handler(CommandHandler("ytb2transcript", self.ytb2transcript_command))
            application.add_handler(CallbackQueryHandler(
                self.toggle_markdown_callback,
                pattern=r"^toggle_md_"
            ))                             
            application.add_handler(CommandHandler("jailbreak", self.jailbreak_command))
            application.add_handler(CallbackQueryHandler(
                self.jailbreak_callback_handler, 
                pattern=r"^jailbreak_"
            ))                                                                   
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
            application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL | filters.AUDIO | filters.VOICE, self.handle_media)) ; logo() ; print(f"\nBot is running...\n")      
            application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

        except Exception as e:
            print(f"Critical error: {str(e).replace(self.config.gemini_api_key, '[REDACTED]')}")
            raise

if __name__ == "__main__":
    config_editor()
    bot = AIBot()
    bot.run()
