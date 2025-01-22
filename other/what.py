# main.py v1.4.46
"""
=== MAINTENANCE AND MODIFICATION GUIDE ===

This Telegram bot integrates Gemini AI, media downloaders, and web conversion tools. Follow these guidelines when modifying:

1. CRITICAL COMPONENTS (Avoid structural changes without testing)
- Configuration System:
  • Modify config/config.json for settings (not Config class logic)
  • Add new env variables ONLY through the Config class
- Security Decorators (@check_user_access and @global_user_access):
  • Preserve user ID validation logic
  • Modify allowed_users list in config.json for access control
  • Use @global_user_access to block a certain feature for everyone
- API Handlers (Gemini/YouTube/Instagram):
  • Keep retry logic and error handling intact
  • Update regex patterns cautiously (INSTAGRAM_URL_REGEX/YOUTUBE_URL_REGEX)

2. SAFE TO MODIFY AREAS
- Command Handlers:
  • Add new commands using @check_user_access decorator
  • Extend help_command() with new features
- File Processing:
  • Add supported extensions via allowed_extensions set
  • Implement new process_file() handlers
- Chat Features:
  • Modify format_reply_context() for different reply formatting
  • Adjust manage_chat_history() token limits

3. MODIFICATION WARNINGS
- Chat History Structure:
  • Changing history format will invalidate existing user histories
  • Test data migration if modifying Chat class
- Media Processing:
  • Maintain base64 encoding for Gemini API compatibility
  • Keep tempfile cleanup procedures
- Dependency Versions:
  • Verify library compatibility before upgrading:
    python-telegram-bot~20.5
    Pillow~10.2
    requests~2.31

4. BEST PRACTICES
- Environment Management:
  • Keep TELEGRAM_TOKEN_KEY and GEMINI_API_KEY in environment
  • Never commit .env files
- Testing:
  • Validate Instagram/YouTube regex changes with URL samples
  • Test file uploads with all allowed extensions
  • Verify history persistence after restarts
- Error Handling:
  • Maintain retry_operation() wrapper for network calls
  • Preserve file cleanup in finally blocks

5. EXTENSION GUIDE
To add new features:
- New Commands:
  1. Create handler with @check_user_access
  2. Add to help_command() text
  3. Register in application.add_handler()
- New Media Types:
  1. Add to allowed_extensions
  2. Implement handle_processed_file() logic
  3. Update get_replied_message_content()
- API Integrations:
  1. Use existing generate_content() pattern
  2. Implement response handling similar to handle_gemini_response()
  3. Add rate limiting via RETRY_DELAY

6. CRITICAL PATHS
- Initialization Flow:
  config_editor() → AIBot() → run()
- Message Processing:
  handle_text() → generate_content() → handle_gemini_response()
- File Pipeline:
  handle_media() → process_file() → handle_processed_file()

=== END OF GUIDE ===
"""

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
from telegram.constants import ParseMode
from telegram import Update, Message, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,  # Added this import
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
from utils.flask.config_editor import config_editor
from utils.commands.insta import InstagramDownloader
from utils.commands.ytb2mp3 import YouTubeDownloader
from utils.commands.web2md import WebToMarkdownConverter
from utils.commands.start import start_command
from utils.commands.help import help_command
from utils.commands.clear import clear_command
from utils.commands.think import think_command
from utils.commands.ytb2transcript import handler as transcript_handler
from telegram.helpers import escape_markdown

def custom_markdown_escape(text: str) -> str:
    """
    Improved Markdown escape function that handles code blocks and quote blocks correctly.
    
    Args:
        text: Input text to escape
        
    Returns:
        Properly escaped text for MarkdownV2 format
    """
    if not isinstance(text, str):
        return str(text)
        
    # First, identify and protect code blocks
    code_blocks = []
    protected_text = text
    code_pattern = r'```(?:\w+)?\n(?:.*?)\n```'
    
    def save_code_block(match):
        code_blocks.append(match.group(0))
        return f"<<CODE_BLOCK_{len(code_blocks)-1}>>"
        
    protected_text = re.sub(code_pattern, save_code_block, protected_text, flags=re.DOTALL)
    
    # Characters that need escaping in MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    
    lines = protected_text.split('\n')
    escaped_lines = []
    
    for line in lines:
        if line.startswith('>'):
            # Handle quote blocks - escape everything except the initial '>'
            quote_content = ''.join([f'\\{c}' if c in escape_chars else c for c in line[1:]])
            escaped_lines.append('>' + quote_content)
        else:
            # Escape all special characters in normal text
            escaped_line = ''.join([f'\\{c}' if c in escape_chars else c for c in line])
            escaped_lines.append(escaped_line)
    
    escaped_text = '\n'.join(escaped_lines)
    
    # Restore code blocks
    for i, block in enumerate(code_blocks):
        escaped_text = escaped_text.replace(f"<<CODE_BLOCK_{i}>>", block)
    
    return escaped_text
    
    
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
            
            await chat.send_message_async(f"{text_response}", role="assistant")
            await self.save_chat_history(user_id, username)
            return text_response
        except Exception as e:
            return f"Error processing file: {str(e)}"

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

# = Web to Markdown =============================================================================================================

    @check_user_access
    async def web2md_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /web2md command to convert webpages to Markdown."""
        await self.web2md_converter.handle_web2md_command(self, update, context)
# = Thinking command ============================================================================================================

    @check_user_access
    async def think_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /think command with detailed reasoning"""
        await think_command.handle_think_command(self, update, context)

# = YouTube Transcript Command ============================================================================================================

    @check_user_access
    async def ytb2transcript_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /ytb2transcript command"""
        await transcript_handler.handle_ytb2transcript_command(self, update, context)
            
# = Basic Commands ============================================================================================================

    @check_user_access
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
        Enhanced function to extract content and metadata from replied-to messages.
        Handles various message types and potential parsing errors.
        
        Args:
            message: The Telegram message object
            
        Returns:
            Optional[dict]: Message content and metadata, or None if not a reply
        """
        if not message.reply_to_message:
            return None
            
        replied_msg = message.reply_to_message
        result = {
            'content': None,
            'role': 'assistant' if replied_msg.from_user.is_bot else 'user',
            'type': 'unknown',
            'metadata': {}
        }
        
        try:
            # Handle text messages
            if replied_msg.text:
                result.update({
                    'content': replied_msg.text,
                    'type': 'text',
                    'metadata': {
                        'length': len(replied_msg.text),
                        'has_entities': bool(replied_msg.entities)
                    }
                })
                
            # Handle photos
            elif replied_msg.photo:
                photo = replied_msg.photo[-1]  # Get highest resolution
                file_obj = await self.retry_operation(photo.get_file)
                
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                    try:
                        await file_obj.download_to_drive(temp_file.name)
                        with Image.open(temp_file.name) as img:
                            img_format = img.format
                            width, height = img.size
                            
                            buf = io.BytesIO()
                            img.save(buf, format='JPEG')
                            img_b64 = base64.b64encode(buf.getvalue()).decode()
                            
                            result.update({
                                'content': [{
                                    'text': '[Image]',
                                    'image_data': img_b64,
                                    'caption': replied_msg.caption or ''
                                }],
                                'type': 'image',
                                'metadata': {
                                    'width': width,
                                    'height': height,
                                    'format': img_format,
                                    'file_size': photo.file_size
                                }
                            })
                    finally:
                        os.unlink(temp_file.name)
                        
            # Handle documents
            elif replied_msg.document:
                doc = replied_msg.document
                if doc.file_name.endswith(tuple(self.allowed_extensions)):
                    file_obj = await self.retry_operation(doc.get_file)
                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                        try:
                            await file_obj.download_to_drive(temp_file.name)
                            with open(temp_file.name, 'r', encoding='utf-8') as f:
                                content = f.read()
                                result.update({
                                    'content': content,
                                    'type': 'document',
                                    'metadata': {
                                        'filename': doc.file_name,
                                        'mime_type': doc.mime_type,
                                        'file_size': doc.file_size
                                    }
                                })
                        except UnicodeDecodeError:
                            result.update({
                                'content': '[Binary document]',
                                'type': 'binary_document',
                                'metadata': {
                                    'filename': doc.file_name,
                                    'mime_type': doc.mime_type,
                                    'file_size': doc.file_size
                                }
                            })
                        finally:
                            os.unlink(temp_file.name)
                else:
                    raise ValueError(f"Unsupported document type: {doc.file_name}")
                    
            # Handle voice/audio messages
            elif replied_msg.voice or replied_msg.audio:
                audio_msg = replied_msg.voice or replied_msg.audio
                result.update({
                    'content': '[Audio message]',
                    'type': 'audio',
                    'metadata': {
                        'duration': audio_msg.duration,
                        'file_size': audio_msg.file_size,
                        'mime_type': getattr(audio_msg, 'mime_type', 'audio/ogg')
                    }
                })
                
        except Exception as e:
            print(f"Error processing replied message: {str(e)}")
            result.update({
                'content': f"[Error processing message: {str(e)}]",
                'type': 'error',
                'metadata': {'error': str(e)}
            })
            
        return result
        
    def format_reply_context(self, reply_info: dict, current_message: str) -> Union[str, list]:
        """
        Enhanced function to format reply context with better metadata handling and error checking.
        
        Args:
            reply_info: Dictionary containing reply message information
            current_message: The current message text
            
        Returns:
            Formatted context as either a string or list depending on content type
        """
        if not reply_info or not isinstance(reply_info, dict):
            return f"USER MESSAGE: {current_message}"
            
        role_label = "AI assistant" if reply_info['role'] == "assistant" else "user"
        metadata = reply_info.get('metadata', {})
        
        try:
            if reply_info['type'] == 'image':
                if not isinstance(reply_info['content'], list) or not reply_info['content']:
                    raise ValueError("Invalid image content format")
                    
                image_content = reply_info['content'][0]
                return [{
                    "text": (
                        f"CONTEXT: Image message reply\n"
                        f"METADATA:\n"
                        f"- Sender: {role_label}\n"
                        f"- Image size: {metadata.get('width', 'unknown')}x{metadata.get('height', 'unknown')}\n"
                        f"- Format: {metadata.get('format', 'unknown')}\n"
                        f"- File size: {metadata.get('file_size', 0) / 1024:.1f}KB\n"
                        f"- Caption: {image_content.get('caption', '[No caption]')}\n"
                        f"IMAGE DATA: [Image follows]\n"
                    )
                }, {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_content.get('image_data', '')
                    }
                }, {
                    "text": f"\nUSER'S REPLY: {current_message}"
                }]
                
            elif reply_info['type'] == 'document':
                return (
                    f"CONTEXT: Document message reply\n"
                    f"METADATA:\n"
                    f"- Sender: {role_label}\n"
                    f"- Filename: {metadata.get('filename', 'unknown')}\n"
                    f"- Type: {metadata.get('mime_type', 'unknown')}\n"
                    f"- Size: {metadata.get('file_size', 0) / 1024:.1f}KB\n\n"
                    f"DOCUMENT CONTENT:\n{reply_info['content']}\n\n"
                    f"USER'S REPLY: {current_message}"
                )
                
            elif reply_info['type'] == 'audio':
                return (
                    f"CONTEXT: Audio message reply\n"
                    f"METADATA:\n"
                    f"- Sender: {role_label}\n"
                    f"- Duration: {metadata.get('duration', 0)}s\n"
                    f"- Type: {metadata.get('mime_type', 'audio/unknown')}\n"
                    f"- Size: {metadata.get('file_size', 0) / 1024:.1f}KB\n\n"
                    f"USER'S REPLY: {current_message}"
                )
                
            elif reply_info['type'] == 'error':
                return (
                    f"CONTEXT: Error in previous message\n"
                    f"ERROR: {metadata.get('error', 'Unknown error')}\n\n"
                    f"USER'S REPLY: {current_message}"
                )
                
            else:  # text or unknown type
                return (
                    f"CONTEXT: Text message reply\n"
                    f"SENDER: {role_label}\n"
                    f"PREVIOUS MESSAGE: {reply_info['content']}\n\n"
                    f"USER'S REPLY: {current_message}"
                )
                
        except Exception as e:
            print(f"Error formatting reply context: {str(e)}")
            return f"CONTEXT: Error formatting reply\nUSER'S REPLY: {current_message}"
    
           
    async def send_response_with_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                      text: str, reply_to_message_id: int = None) -> Optional[list]:
        """
        Enhanced function to send responses with proper chunking and markdown toggle support.
        
        Args:
            update: Telegram update object
            context: Bot context
            text: Text to send
            reply_to_message_id: Optional message ID to reply to
            
        Returns:
            List of sent messages or None if error
        """
        if not text:
            return None
            
        try:
            if 'message_cache' not in context.chat_data:
                context.chat_data['message_cache'] = {}
                
            callback_data = f"toggle_md_{uuid.uuid4()}"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("Toggle Markdown", callback_data=callback_data)
            ]])
            
            # Initialize message tracking
            sent_messages = []
            safe_text = custom_markdown_escape(text)
            
            # Split text into chunks if needed
            MAX_LENGTH = 4096
            text_chunks = []
            safe_chunks = []
            
            for i in range(0, len(text), MAX_LENGTH):
                text_chunks.append(text[i:i + MAX_LENGTH])
                safe_chunks.append(safe_text[i:i + MAX_LENGTH])
            
            # Send each chunk
            for i, (chunk, safe_chunk) in enumerate(zip(text_chunks, safe_chunks)):
                is_last_chunk = i == len(text_chunks) - 1
                
                try:
                    sent_msg = await self.retry_operation(
                        update.message.reply_text,
                        safe_chunk,
                        reply_to_message_id=reply_to_message_id if i == 0 else None,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        reply_markup=keyboard if is_last_chunk else None
                    )
                    sent_messages.append(sent_msg)
                    
                except telegram.error.BadRequest as e:
                    if "Can't parse entities" in str(e):
                        # Fallback to plain text if markdown fails
                        sent_msg = await self.retry_operation(
                            update.message.reply_text,
                            chunk,
                            reply_to_message_id=reply_to_message_id if i == 0 else None,
                            reply_markup=keyboard if is_last_chunk else None
                        )
                        sent_messages.append(sent_msg)
                    else:
                        raise
    
            # Cache message data for toggle functionality
            if sent_messages:
                context.chat_data['message_cache'][callback_data] = {
                    'original_text': text,
                    'safe_text': safe_text,
                    'messages': [msg.message_id for msg in sent_messages],
                    'markdown_mode': True,
                    'chunks': list(zip(text_chunks, safe_chunks))
                }
                
            return sent_messages
            
        except Exception as e:
            error_message = f"Error sending message: {str(e)}"
            try:
                await self.retry_operation(
                    update.message.reply_text,
                    error_message,
                    reply_to_message_id=reply_to_message_id
                )
            except Exception as send_error:
                print(f"Critical error sending message: {str(send_error)}")
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
            
            # In handle_text:
            text_response = await self.handle_gemini_response(response)
            escaped_response = custom_markdown_escape(text_response)
            await self.send_response_with_toggle(update, context, escaped_response)
            
            await self.save_chat_history(user_id, username)
            
            # Use the new utility method to send the response
            # await self.send_response_with_toggle(update, context, text_response)
                
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
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
            await self.send_response_with_toggle(update, context, custom_markdown_escape(result))

        except Exception as e:
            error_message = f"Error handling media: {str(e)}"
            await self.send_response_with_toggle(update, context, error_message)
            
    async def toggle_markdown_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Enhanced callback handler for toggling between markdown and plain text display.
        
        Args:
            update: Telegram update object
            context: Bot context
        """
        query = update.callback_query
        await query.answer()
        
        try:
            cache_key = query.data
            message_data = context.chat_data['message_cache'].get(cache_key)
            
            if not message_data:
                print(f"No cached data found for key: {cache_key}")
                await query.edit_message_reply_markup(reply_markup=None)
                return
            
            # Toggle mode
            new_mode = not message_data['markdown_mode']
            button_text = "Show Plain Text" if new_mode else "Render Markdown"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(button_text, callback_data=cache_key)
            ]])
            
            # Update each message chunk
            for msg_id in message_data['messages']:
                chunk_index = message_data['messages'].index(msg_id)
                is_last_chunk = chunk_index == len(message_data['messages']) - 1
                
                try:
                    current_chunks = message_data['chunks'][chunk_index]
                    text_to_use = current_chunks[1] if new_mode else current_chunks[0]
                    
                    await context.bot.edit_message_text(
                        chat_id=query.message.chat_id,
                        message_id=msg_id,
                        text=text_to_use,
                        parse_mode=ParseMode.MARKDOWN_V2 if new_mode else None,
                        reply_markup=keyboard if is_last_chunk else None
                    )
                    
                except telegram.error.BadRequest as e:
                    if "Can't parse entities" in str(e):
                        # Fallback to safe text
                        await context.bot.edit_message_text(
                            chat_id=query.message.chat_id,
                            message_id=msg_id,
                            text=current_chunks[1],  # Use safe text
                            parse_mode=None,
                            reply_markup=keyboard if is_last_chunk else None
                        )
                    else:
                        print(f"Error updating message {msg_id}: {str(e)}")
            
            # Update cached state
            message_data['markdown_mode'] = new_mode
            context.chat_data['message_cache'][cache_key] = message_data
            
        except Exception as e:
            print(f"Error in toggle callback: {str(e)}")
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
        




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
            application.add_handler(CommandHandler("insta", self.insta_command))
            application.add_handler(CommandHandler("instaFile", self.insta_file_command))
            application.add_handler(CommandHandler("ytb2mp3", self.ytb2mp3_command))
            application.add_handler(CommandHandler("web2md", self.web2md_command))
            application.add_handler(CommandHandler("think", self.think_command))
            application.add_handler(CommandHandler("ytb2transcript", self.ytb2transcript_command))
            
            # Add callback query handler for Markdown toggle
            application.add_handler(CallbackQueryHandler(
                self.toggle_markdown_callback,
                pattern=r"^toggle_md_"
            ))
                             
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
            application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL | filters.AUDIO | filters.VOICE, self.handle_media)); print(f"\nBot is running...\n")      
            application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

        except Exception as e:
            print(f"Critical error: {str(e)}")
            raise





class MediaProcessor:
    """New class to handle media processing operations"""
    
    def __init__(self, allowed_extensions: set):
        self.allowed_extensions = allowed_extensions
        self.temp_files = set()  # Track temporary files
        
    def __del__(self):
        """Cleanup any remaining temporary files"""
        self.cleanup_temp_files()
        
    def cleanup_temp_files(self):
        """Clean up all registered temporary files"""
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error cleaning up temp file {file_path}: {str(e)}")
        self.temp_files.clear()

    async def process_file(self, message: Message, download_func: Callable) -> dict:
        """
        Enhanced file processing with better error handling and resource management.
        
        Args:
            message: Telegram message containing the file
            download_func: Function to download the file
            
        Returns:
            Dict containing processed file information and content
        """
        temp_file = None
        try:
            # Create temporary file with appropriate extension
            file_extension = self.get_file_extension(message)
            with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
                self.temp_files.add(temp_file.name)
                await download_func(temp_file.name)
                
                return await self.handle_processed_file(temp_file.name, message)
                
        except Exception as e:
            raise ProcessingError(f"File processing error: {str(e)}")
        finally:
            if temp_file and temp_file.name in self.temp_files:
                self.cleanup_temp_files()

    def get_file_extension(self, message: Message) -> str:
        """
        Determine appropriate file extension based on message type.
        
        Args:
            message: Telegram message
            
        Returns:
            String containing the file extension
        """
        if message.document:
            original_extension = os.path.splitext(message.document.file_name)[1].lower()
            if original_extension in self.allowed_extensions:
                return original_extension
            raise ValueError(f"Unsupported file type: {original_extension}")
            
        elif message.photo:
            return '.jpg'
        elif message.voice:
            return '.ogg'
        elif message.audio:
            return self.get_audio_extension(message.audio)
        else:
            raise ValueError("Unsupported message type")
            
    def get_audio_extension(self, audio) -> str:
        """
        Determine audio file extension based on mime type.
        
        Args:
            audio: Telegram audio object
            
        Returns:
            String containing the audio file extension
        """
        mime_to_ext = {
            'audio/mpeg': '.mp3',
            'audio/mp4': '.m4a',
            'audio/ogg': '.ogg',
            'audio/wav': '.wav',
            'audio/x-wav': '.wav'
        }
        return mime_to_ext.get(audio.mime_type, '.mp3')

    async def handle_processed_file(self, file_path: str, message: Message) -> dict:
        """
        Process different types of files and prepare them for AI processing.
        
        Args:
            file_path: Path to the temporary file
            message: Original Telegram message
            
        Returns:
            Dict containing processed content and metadata
        """
        result = {
            'content': None,
            'metadata': {
                'file_type': None,
                'mime_type': None,
                'file_size': os.path.getsize(file_path),
                'timestamp': datetime.now().isoformat()
            }
        }
        
        try:
            if message.photo:
                result.update(await self.process_image(file_path, message))
            elif message.document:
                result.update(await self.process_document(file_path, message))
            elif message.audio or message.voice:
                result.update(await self.process_audio(file_path, message))
            else:
                raise ValueError("Unsupported message type")
                
            return result
            
        except Exception as e:
            raise ProcessingError(f"Error processing file: {str(e)}")

    async def process_image(self, file_path: str, message: Message) -> dict:
        """
        Process image files with proper error handling and metadata extraction.
        
        Args:
            file_path: Path to the temporary image file
            message: Original Telegram message
            
        Returns:
            Dict containing processed image data and metadata
        """
        try:
            with Image.open(file_path) as img:
                # Convert RGBA to RGB if necessary
                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                
                # Resize if image is too large
                max_dimension = 1024
                if max(img.size) > max_dimension:
                    ratio = max_dimension / max(img.size)
                    new_size = tuple(int(dim * ratio) for dim in img.size)
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Convert to JPEG and get base64
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=85)
                img_b64 = base64.b64encode(buf.getvalue()).decode()
                
                return {
                    'content': [{
                        'text': caption_text,
                        'image_data': img_b64
                    }],
                    'metadata': {
                        'file_type': 'image',
                        'mime_type': 'image/jpeg',
                        'width': img.size[0],
                        'height': img.size[1],
                        'mode': img.mode,
                        'format': img.format,
                        'caption': message.caption or ''
                    }
                }
                
        except Exception as e:
            raise ProcessingError(f"Image processing error: {str(e)}")

    async def process_document(self, file_path: str, message: Message) -> dict:
        """
        Process document files with encoding detection and error handling.
        
        Args:
            file_path: Path to the temporary document file
            message: Original Telegram message
            
        Returns:
            Dict containing processed document content and metadata
        """
        try:
            # Try different encodings
            encodings = ['utf-8', 'latin1', 'cp1252']
            content = None
            used_encoding = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                        used_encoding = encoding
                        break
                except UnicodeDecodeError:
                    continue
                    
            if content is None:
                raise ValueError("Could not decode file with any supported encoding")
                
            return {
                'content': content,
                'metadata': {
                    'file_type': 'document',
                    'mime_type': message.document.mime_type,
                    'filename': message.document.file_name,
                    'encoding': used_encoding
                }
            }
            
        except Exception as e:
            raise ProcessingError(f"Document processing error: {str(e)}")

    async def process_audio(self, file_path: str, message: Message) -> dict:
        """
        Process audio files with proper metadata extraction.
        
        Args:
            file_path: Path to the temporary audio file
            message: Original Telegram message
            
        Returns:
            Dict containing processed audio data and metadata
        """
        try:
            audio_msg = message.audio or message.voice
            with open(file_path, 'rb') as f:
                audio_b64 = base64.b64encode(f.read()).decode()
                
            return {
                'content': [{
                    'text': f"Audio message - Duration: {audio_msg.duration}s",
                    'audio_data': audio_b64
                }],
                'metadata': {
                    'file_type': 'audio',
                    'mime_type': getattr(audio_msg, 'mime_type', 'audio/ogg'),
                    'duration': audio_msg.duration,
                    'file_size': audio_msg.file_size,
                    'voice': bool(message.voice)
                }
            }
            
        except Exception as e:
            raise ProcessingError(f"Audio processing error: {str(e)}")

class ProcessingError(Exception):
    """Custom exception for file processing errors"""
    pass






if __name__ == "__main__":
    config_editor()
    bot = AIBot()
    bot.run()
