import re
import os
import asyncio
from typing import Dict, Optional
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
import requests
from urllib.parse import urlparse, parse_qs
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler
)

# Conversation states
LINK, LANGUAGE, FORMAT, CONFIRM = range(4)

class YouTubeTranscriptHandler:
    def __init__(self):
        self.sessions: Dict[int, dict] = {}
        
    def get_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from YouTube URL."""
        parsed_url = urlparse(url)
        if parsed_url.netloc == 'youtu.be':
            return parsed_url.path.strip('/')
        if parsed_url.netloc in ['www.youtube.com', 'youtube.com']:
            if parsed_url.path == '/watch':
                return parse_qs(parsed_url.query).get('v', [None])[0]
            if parsed_url.path.startswith('/embed/'):
                return parsed_url.path.split('/')[2]
            if parsed_url.path.startswith('/v/'):
                return parsed_url.path.split('/')[2]
        return None

    def get_video_title(self, video_id: str) -> str:
        """Fetch video title using web scraping."""
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            response = requests.get(url, timeout=10)
            title_match = re.search(r'<title>(.*?)</title>', response.text)
            return title_match.group(1).replace(' - YouTube', '').strip() if title_match else "Untitled Video"
        except Exception:
            return "Untitled Video"

    async def start_transcript_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the transcript conversation."""
        user_id = update.effective_user.id
        self.sessions[user_id] = {'stage': LINK}
        
        await update.message.reply_text(
            "🎥 Please send me a YouTube video link to generate transcript:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ])
        )
        return LINK

    async def handle_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle YouTube link input."""
        user_id = update.effective_user.id
        url = update.message.text.strip()
        video_id = self.get_video_id(url)

        if not video_id:
            await update.message.reply_text("❌ Invalid YouTube URL. Please try again:")
            return LINK

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except (TranscriptsDisabled, VideoUnavailable):
            await update.message.reply_text("❌ Transcripts not available for this video.")
            return ConversationHandler.END

        session_data = {
            'video_id': video_id,
            'available_langs': [t.language_code for t in transcript_list],
            'video_title': self.get_video_title(video_id)
        }
        self.sessions[user_id] = session_data

        keyboard = [
            [InlineKeyboardButton(lang, callback_data=f"lang_{lang}")]
            for lang in session_data['available_langs']
        ]
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])

        await update.message.reply_text(
            f"🌐 Available languages for '{session_data['video_title']}':\n"
            f"{', '.join(session_data['available_langs'])}\n\n"
            "Please choose a language:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return LANGUAGE

    async def handle_language(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle language selection."""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        lang = query.data.split('_')[1]

        self.sessions[user_id]['language'] = lang
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("With Timestamps ⏱️", callback_data="format_timestamp")],
            [InlineKeyboardButton("Plain Text 📝", callback_data="format_plain")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
        
        await query.edit_message_text(
            "📝 Choose transcript format:",
            reply_markup=keyboard
        )
        return FORMAT

    async def handle_format(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle format selection."""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        fmt = query.data.split('_')[1]

        self.sessions[user_id]['format'] = fmt
        
        transcript_info = (
            f"Video: {self.sessions[user_id]['video_title']}\n"
            f"Language: {self.sessions[user_id]['language']}\n"
            f"Format: {fmt.capitalize()}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Generate Transcript", callback_data="confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
        
        await query.edit_message_text(
            f"📄 Confirm settings:\n{transcript_info}",
            reply_markup=keyboard
        )
        return CONFIRM

    async def generate_transcript(self, user_id: int) -> str:
        """Generate transcript text with selected settings."""
        session = self.sessions[user_id]
        transcript = YouTubeTranscriptApi.get_transcript(
            session['video_id'],
            languages=[session['language']]
        )

        lines = [
            f"Title: {session['video_title']}",
            f"Video ID: {session['video_id']}",
            f"Language: {session['language']}",
            "\nTranscript:\n"
        ]

        for entry in transcript:
            if session['format'] == 'timestamp':
                time = f"{int(entry['start']//3600):02}:{int(entry['start']%3600//60):02}:{int(entry['start']%60):02}"
                lines.append(f"{time} - {entry['text']}")
            else:
                lines.append(entry['text'])

        return '\n'.join(lines)

    async def handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle final confirmation and generate transcript."""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if user_id not in self.sessions:
            await query.edit_message_text("❌ Session expired. Please start over.")
            return ConversationHandler.END

        try:
            await query.edit_message_text("⏳ Generating transcript... This may take a moment.")
            transcript_text = await self.generate_transcript(user_id)
            
            # Send as file if over 4000 characters
            if len(transcript_text) > 4000:
                filename = f"{self.sessions[user_id]['video_title'][:50]}.txt"
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=transcript_text.encode('utf-8'),
                    filename=filename,
                    caption="Here's your transcript 📄"
                )
            else:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"📄 Transcript:\n\n{transcript_text}"
                )
                
        except Exception as e:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ Error generating transcript: {str(e)}"
            )
        finally:
            del self.sessions[user_id]
            
        return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        user_id = update.effective_user.id
        if user_id in self.sessions:
            del self.sessions[user_id]
            
        await update.message.reply_text("❌ Operation cancelled.") if update.message else None
        return ConversationHandler.END

    def get_conversation_handler(self) -> ConversationHandler:
        """Return configured conversation handler."""
        return ConversationHandler(
            entry_points=[CommandHandler('ytb2transcript', self.start_transcript_process)],
            states={
                LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_link)],
                LANGUAGE: [CallbackQueryHandler(self.handle_language, pattern=r'^lang_')],
                FORMAT: [CallbackQueryHandler(self.handle_format, pattern=r'^format_')],
                CONFIRM: [CallbackQueryHandler(self.handle_confirmation, pattern='^confirm$')]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel),
                CallbackQueryHandler(self.cancel, pattern='^cancel$')
            ],
            allow_reentry=True
        )