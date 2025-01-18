# main.py v1.4.0
import os
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
from telegram import Update, Message
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.error import TimedOut, NetworkError, RetryAfter
from PIL import Image
import io
import urllib.parse
import shutil
from pathlib import Path
from utils.instagram.instagram_downloader import InstagramDownloader
from utils.ytb.ytb2mp3 import YouTubeDownloader
from datetime import datetime
from utils.flask.config_editor import config_editor
from utils.tools.web2md import WebToMarkdownConverter

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
    MAX_RETRIES = 4
    RETRY_DELAY = 3  # seconds
    HISTORY_DIR = "history"
    GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    INSTAGRAM_URL_REGEX = re.compile(
        r'(?:https?://)?(?:www\.)?instagram\.com/(?:p/|reel/)([\w-]+)')

    def __init__(self):
        self.config = Config()
        self.chat_history = {}
        self.history_dir = self.HISTORY_DIR
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

        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)

    async def generate_content(self, contents, stream=False):
        endpoint = "streamGenerateContent" if stream else "generateContent"
        url = f"{self.api_url}:{endpoint}?{'alt=sse&' if stream else ''}key={self.config.gemini_api_key}"
        
        # Convert safety settings to proper format
        # safety_settings_list = [
            # {
                # "category": item["category"],
                # "threshold": item["threshold"]
            # } for item in self.config.safety_settings
        # ]
        
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
            print(f"Error making request to Gemini API: {str(e)}")
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
            print(f"Error handling Gemini response: {str(e)}")
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
                    f"Operation failed with {str(e)}, retrying in {delay} seconds..."
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

    def get_history_file_path(self, user_id: str, username: str) -> str:
        """Generate the file path for a user's chat history."""
        username = username.replace(" ", "_") if username else "unknown"
        filename = f"{username}_{user_id}.pkl"
        return os.path.join(self.history_dir, filename)

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
        """Save chat history to a pickle file."""
        file_path = self.get_history_file_path(user_id, username)
        try:
            with open(file_path, 'wb') as f:
                pickle.dump(self.chat_history[user_id].history, f)
        except Exception as e:
            print(f"Error saving chat history to {file_path}: {e}")

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
            return f"An error occurred: {str(e)}"
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
            
            await chat.send_message_async(f"assistant: {text_response}", role="assistant")
            await self.save_chat_history(user_id, username)
            return text_response
        except Exception as e:
            return f"Error processing file: {str(e)}"






# = Instagram Downloader =============================================================================================================

# handling Instagram commands

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

# = Web to Markdown =============================================================================================================

    @check_user_access
    async def web2md_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /web2md command to convert webpages to Markdown."""
        await self.web2md_converter.handle_web2md_command(self, update, context)
        
# ==============================================================================================================

#   @check_user_access
    async def start(self, update: Update,
                    context: ContextTypes.DEFAULT_TYPE) -> None:
        """Start command handler with user logging functionality."""
        user = update.effective_user
        username = str(user.username) if user.username else f"user_{user.id}"
        user_id = user.id

        # Create user data directory if it doesn't exist
        os.makedirs('data/users', exist_ok=True)

        # Prepare user data
        user_data = {
            'user_id': user_id,
            'username': username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_bot': user.is_bot,
            'language_code': user.language_code,
            'can_join_groups': user.can_join_groups,
            'can_read_all_group_messages': user.can_read_all_group_messages,
            'supports_inline_queries': user.supports_inline_queries,
            'first_seen': datetime.now().isoformat(),
            'chat_id': update.message.chat_id,
            'chat_type': update.message.chat.type,
        }

        # Save user data to JSON file
        filename = f'data/users/{username}_{user_id}.json'
        try:
            existing_data = {}
            if os.path.exists(filename):
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:  # Only try to load if file is not empty
                            existing_data = json.loads(content)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    print(
                        f"Warning: Could not read existing file {filename}: {e}"
                    )
                    # Backup the corrupted file
                    if os.path.exists(filename):
                        backup_name = f"{filename}.bak.{int(datetime.now().timestamp())}"
                        os.rename(filename, backup_name)
                        print(f"Backed up corrupted file to {backup_name}")

            # Update user data with existing first_seen if available
            if existing_data and 'first_seen' in existing_data:
                user_data['first_seen'] = existing_data['first_seen']
            user_data['last_seen'] = datetime.now().isoformat()

            # Write the updated data
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(user_data, f, indent=4, ensure_ascii=False)

        except Exception as e:
            print(f"Error handling user data for {username}: {str(e)}")
            # Continue with the welcome message even if logging fails

        # Send welcome message
        await self.retry_operation(
            update.message.reply_text,
            f"""Welcome {user.first_name} !\nI'm your AkiBot. Send me text, images, documents or audio and I will respond.\nUse /help for more info.""",
            # parse_mode='MarkdownV2'
        )

    @check_user_access
    async def help_command(self, update: Update,
                           context: ContextTypes.DEFAULT_TYPE) -> None:
        """Help command handler."""
        help_text = f"""
<b>Available Commands:</b>

- /start » Start the bot and get a greeting message.
- /help » Show this help message.
- /clear » Clear the conversation history.

<b>Capabilities:</b>

- Send text messages to chat with the AI.
- Send images with optional captions to use the vision capabilities.
- Send text-based documents for document understanding.
- Send audio files for audio processing.
- The bot maintains chat history context.

"""
        await self.retry_operation(update.message.reply_text,
                                   help_text,
                                   parse_mode='HTML')

    @check_user_access
    async def clear(self, update: Update,
                    context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clear command handler."""
        user_id = str(update.effective_user.id)
        username = str(update.effective_user.username)
        if user_id in self.chat_history:
            del self.chat_history[user_id]
        file_path = self.get_history_file_path(user_id, username)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error deleting history file {file_path}: {e}")
        await self.retry_operation(update.message.reply_text,
                                   "Chat history cleared.",
                                   parse_mode='HTML')

# ==============================================================================================================

    # still can't reply to audio 
    async def get_replied_message_content(self, message: Message) -> Optional[dict]:
        """
        Extract content and metadata from the replied-to message.
        Returns a dictionary containing:
        - content: The message content
        - role: 'assistant' or 'user'
        - type: The type of message (text, image, document, audio)
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
            elif replied_msg.caption:
                result['content'] = replied_msg.caption
                result['type'] = 'caption'
            elif replied_msg.photo:
                file_obj = await self.retry_operation(replied_msg.photo[-1].get_file)
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                    await file_obj.download_to_drive(temp_file.name)
                    with Image.open(temp_file.name) as img:
                        buf = io.BytesIO()
                        img.save(buf, format='JPEG')
                        img_b64 = base64.b64encode(buf.getvalue()).decode()
                        result['content'] = [{
                            "text": "[Image]"
                        }, {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": img_b64
                            }
                        }]
                        result['type'] = 'image'
            elif replied_msg.document and replied_msg.document.file_name.endswith(tuple(self.allowed_extensions)):
                file_obj = await self.retry_operation(replied_msg.document.get_file)
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    await file_obj.download_to_drive(temp_file.name)
                    with open(temp_file.name, 'r', encoding='utf-8') as f:
                        result['content'] = f.read()
                        result['type'] = 'document'
            elif replied_msg.voice or replied_msg.audio:
                # Handle audio replies with proper audio data
                audio_msg = replied_msg.voice or replied_msg.audio
                file_obj = await self.retry_operation(audio_msg.get_file)
                
                with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
                    await file_obj.download_to_drive(temp_file.name)
                    with open(temp_file.name, 'rb') as f:
                        audio_b64 = base64.b64encode(f.read()).decode()
                        
                        # Include audio metadata
                        duration = audio_msg.duration  # Duration in seconds
                        file_size = audio_msg.file_size  # Size in bytes
                        mime_type = "audio/ogg"
                        if replied_msg.audio:
                            mime_type = replied_msg.audio.mime_type or mime_type
                            
                        result['content'] = [{
                            "text": f"[Audio file - Duration: {duration}s, Size: {file_size} bytes]"
                        }, {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": audio_b64
                            }
                        }]
                        result['type'] = 'audio'
                
        except Exception as e:
            print(f"Error processing replied message: {str(e)}")
            result['content'] = "[Error processing previous message]"
            result['type'] = 'error'
            
        return result
        
    
    def format_reply_context(self, reply_info: dict, current_message: str) -> Union[str, list]:
        """
        Format the reply context with role indicators.
        """
        if reply_info['type'] == 'image':
            context_parts = reply_info['content']
            context_parts[0]['text'] = f"{reply_info['role']}: [Image]"
            return context_parts
        else:
            context = f"""{reply_info['role']}: {reply_info['content']}
    user: {current_message}"""
            return context
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Text message handler with role indicators."""
        user_id = str(update.effective_user.id)
        username = str(update.effective_user.username)
        await self.initialize_chat(user_id, username)
    
        text = update.message.text
        
        if self.INSTAGRAM_URL_REGEX.search(text) or self.YOUTUBE_URL_REGEX.search(text):
            return await self.handle_media_urls(update, text)
    
        try:
            chat = self.chat_history[user_id]
            reply_info = await self.get_replied_message_content(update.message)
            
            if reply_info:
                formatted_context = self.format_reply_context(reply_info, text)
                if isinstance(formatted_context, list):
                    await chat.send_message_async(formatted_context, role="user")
                else:
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
            
            if len(text_response) > 4096:
                for chunk in [text_response[i:i+4096] for i in range(0, len(text_response), 4096)]:
                    await self.retry_operation(
                        update.message.reply_text,
                        chunk
                    )
            else:
                await self.retry_operation(
                    update.message.reply_text,
                    text_response
                )
                
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            await self.retry_operation(
                update.message.reply_text,
                error_message
            )
    
    async def handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Media message handler with role indicators."""
        user_id = str(update.effective_user.id)
        username = str(update.effective_user.username)
        await self.initialize_chat(user_id, username)
    
        try:
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
    
            if update.message.photo:
                file_obj = await self.retry_operation(update.message.photo[-1].get_file)
                result = await self.process_file(update.message, lambda path: file_obj.download_to_drive(path))
            elif update.message.document:
                file_extension = os.path.splitext(update.message.document.file_name)[1].lower()
                if file_extension not in self.allowed_extensions:
                    await self.retry_operation(update.message.reply_text, "Unsupported document type.")
                    return
                file_obj = await self.retry_operation(update.message.document.get_file)
                result = await self.process_file(update.message, lambda path: file_obj.download_to_drive(path))
            elif update.message.audio or update.message.voice:
                file_obj = await self.retry_operation((update.message.audio or update.message.voice).get_file)
                result = await self.process_file(update.message, lambda path: file_obj.download_to_drive(path))
            else:
                result = "Unsupported media type"
    
            await self.retry_operation(update.message.reply_text, result)
            
        except Exception as e:
            await self.retry_operation(
                update.message.reply_text,
                f"Error handling media: {str(e)}"
            )
    
    












    # @check_user_access
    # async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # """Text message handler with improved error handling and response processing."""
        # user_id = str(update.effective_user.id)
        # username = str(update.effective_user.username)
        # await self.initialize_chat(user_id, username)
    
        # text = update.message.text
    
        # # Handle special URLs first (Instagram, YouTube)
        # if self.INSTAGRAM_URL_REGEX.search(text) or self.YOUTUBE_URL_REGEX.search(text):
            # return await self.handle_media_urls(update, text)
    
        # try:
            # chat = self.chat_history[user_id]
            # await chat.send_message_async(text, role="user")
            
            # # Generate response with retry logic
            # response = await self.retry_operation(
                # self.generate_content,
                # chat.history,
                # stream=False
            # )
            
            # # Process the response
            # text_response = await self.handle_gemini_response(response)
            
            # # Save AI response to history
            # await chat.send_message_async(text_response, role="assistant")
            # await self.save_chat_history(user_id, username)
            
            # # Send response in chunks if too long
            # if len(text_response) > 4096:
                # for chunk in [text_response[i:i+4096] for i in range(0, len(text_response), 4096)]:
                    # await self.retry_operation(
                        # update.message.reply_text,
                        # chunk
                    # )
            # else:
                # await self.retry_operation(
                    # update.message.reply_text,
                    # text_response
                # )
                
        # except Exception as e:
            # error_message = f"An error occurred: {str(e)}"
            # await self.retry_operation(
                # update.message.reply_text,
                # error_message
            # )
                
    # @check_user_access
    # async def handle_media(self, update: Update,
                           # context: ContextTypes.DEFAULT_TYPE) -> None:
        # """Media message handler with retry logic."""
        # user_id = str(update.effective_user.id)
        # username = str(update.effective_user.username)
        # await self.initialize_chat(user_id, username)

        # try:
            # if update.message.photo:
                # file_obj = await self.retry_operation(
                    # update.message.photo[-1].get_file)
                # result = await self.process_file(
                    # update.message,
                    # lambda path: file_obj.download_to_drive(path))
            # elif update.message.document:
                # file_extension = os.path.splitext(
                    # update.message.document.file_name)[1].lower()
                # if file_extension not in self.allowed_extensions:
                    # await self.retry_operation(update.message.reply_text,
                                               # "Unsupported document type.")
                    # return
                # file_obj = await self.retry_operation(
                    # update.message.document.get_file)
                # result = await self.process_file(
                    # update.message,
                    # lambda path: file_obj.download_to_drive(path))
            # elif update.message.audio or update.message.voice:
                # file_obj = await self.retry_operation(
                    # (update.message.audio or update.message.voice).get_file)
                # result = await self.process_file(
                    # update.message,
                    # lambda path: file_obj.download_to_drive(path))
            # else:
                # result = "Unsupported media type"

            # await self.retry_operation(
                # update.message.reply_text,
                # result,
                # # parse_mode='Markdown'
            # )
        # except Exception as e:
            # await self.retry_operation(update.message.reply_text,
                                       # f"Error handling media: {str(e)}")








    async def count_tokens(self, contents):
        """Count tokens in the content to manage context window."""
        url = f"{self.api_url}:countTokens?key={self.config.gemini_api_key}"
        
        try:
            response = requests.post(url, headers=self.headers, json={"contents": contents})
            response.raise_for_status()
            return response.json().get("totalTokens", 0)
        except Exception as e:
            print(f"Error counting tokens: {str(e)}")
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

            application.add_handler(CommandHandler("insta",
                                                   self.insta_command))
            application.add_handler(
                CommandHandler("instaFile", self.insta_file_command))

            application.add_handler(
                CommandHandler("ytb2mp3", self.ytb2mp3_command))
            application.add_handler(CommandHandler("web2md", self.web2md_command))
                


            application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               self.handle_text))
            application.add_handler(
                MessageHandler(
                    filters.PHOTO | filters.Document.ALL | filters.AUDIO
                    | filters.VOICE, self.handle_media))        

            print(f"\nBot is running...\n")
            
            application.run_polling(drop_pending_updates=True,
                                    allowed_updates=Update.ALL_TYPES)

        except Exception as e:
            print(f"Critical error: {str(e)}")
            raise

if __name__ == "__main__":
    config_editor()
    bot = AIBot()
    bot.run()
