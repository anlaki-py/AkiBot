# ytb2transcript.py v1.0.3
import re
import io
import os
import requests
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from telegram import Update, InputFile, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from typing import Optional, Dict, Any

class YouTubeTranscriptHandler:
    CANCEL_COMMAND = '/cancel'
    FORMAT_TYPES = {
        'With Timestamps': 'timestamp',
        'Plain Text': 'plain'
    }
    
    def __init__(self):
        self.states = {}

    async def handle_ytb2transcript_command(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Initiate transcript generation flow."""
        keyboard = [[self.CANCEL_COMMAND]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "📝 Please send the YouTube video URL.\n"
            f"Send {self.CANCEL_COMMAND} at any time to stop the process.",
            reply_markup=reply_markup
        )
        context.chat_data['transcript_state'] = 'awaiting_url'

    async def process_transcript_steps(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle multi-step transcript generation process."""
        user_input = update.message.text

        # Handle cancel command first, before any other processing
        if user_input.lower() == self.CANCEL_COMMAND.lower():
            await self._cancel_operation(update, context)
            return

        try:
            state = context.chat_data.get('transcript_state')
            if not state:
                await update.message.reply_text(
                    "❌ Session expired. Please start again with /ytb2transcript",
                    reply_markup=ReplyKeyboardRemove()
                )
                return

            if state == 'awaiting_url':
                await self._process_url_input(bot, update, context)
            elif state == 'awaiting_language':
                await self._process_language_input(bot, update, context)
            elif state == 'awaiting_format':
                await self._process_format_input(bot, update, context)
                
        except Exception as e:
            await self._handle_error(update, context, str(e))

    async def _cancel_operation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Cancel the current operation and clean up."""
        context.chat_data.clear()  # Clear all chat data
        await update.message.reply_text(
            "✅ Operation cancelled. You can start again with /ytb2transcript",
            reply_markup=ReplyKeyboardRemove()
        )

    async def _process_url_input(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process YouTube URL and check available languages."""
        url = update.message.text
        video_id = self._get_video_id(url)
        
        if not video_id:
            await self._handle_error(update, context, "Invalid YouTube URL. Please provide a valid URL.")
            return
            
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            available_langs = [t.language_code for t in transcript_list._manually_created_transcripts.values()]
            available_langs.extend([t.language_code for t in transcript_list._generated_transcripts.values()])
            
            if not available_langs:
                raise NoTranscriptFound(video_id)
                
            context.chat_data.update({
                'video_id': video_id,
                'available_langs': available_langs,
                'transcript_state': 'awaiting_language'
            })
            
            # Create keyboard with available languages and cancel button
            keyboard = [[lang] for lang in available_langs]
            keyboard.append([self.CANCEL_COMMAND])
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            
            await update.message.reply_text(
                "🌐 Available languages:\n" + 
                "\n".join([f"• {lang}" for lang in available_langs]) + 
                "\n\nPlease select a language code from above.",
                reply_markup=reply_markup
            )
            
        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
            await self._handle_error(update, context, f"Transcript error: {str(e)}")
        except Exception as e:
            await self._handle_error(update, context, f"Error processing URL: {str(e)}")

    async def _process_language_input(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle language selection and prompt for format."""
        lang = update.message.text.lower()
        available_langs = context.chat_data.get('available_langs', [])
        
        if lang not in available_langs:
            await self._handle_error(
                update,
                context,
                "Invalid language code. Please choose from available languages."
            )
            return
            
        context.chat_data.update({
            'language': lang,
            'transcript_state': 'awaiting_format'
        })
        
        # Create keyboard with format names
        keyboard = [[format_name] for format_name in self.FORMAT_TYPES.keys()]
        keyboard.append([self.CANCEL_COMMAND])
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "📝 Choose transcript format:",
            reply_markup=reply_markup
        )

    async def _process_format_input(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generate and send transcript based on user preferences."""
        format_choice = update.message.text
        
        # Check if the input matches any of our format types
        format_type = None
        for display_name, internal_name in self.FORMAT_TYPES.items():
            if format_choice == display_name:
                format_type = internal_name
                break
                
        if not format_type:
            await self._handle_error(
                update,
                context,
                "Invalid format choice. Please select from the available options."
            )
            return
            
        video_id = context.chat_data['video_id']
        lang = context.chat_data['language']
        
        try:
            await update.message.reply_text(
                "⏳ Generating transcript... Please wait.",
                reply_markup=ReplyKeyboardRemove()
            )
            
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
            title = await self._get_video_title(video_id)
            file_content = self._format_transcript(transcript, format_type, video_id, lang, title)
            
            await update.message.reply_document(
                document=InputFile(io.StringIO(file_content), filename=f"{title[:50]}_transcript.txt"),
                caption=f"📄 {title}"
            )
            
        except Exception as e:
            await self._handle_error(update, context, f"Error generating transcript: {str(e)}")
        finally:
            context.chat_data.clear()

    async def _handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE, error_message: str) -> None:
        """Handle errors and clean up context if necessary."""
        context.chat_data.clear()  # Clear chat data on error
        await update.message.reply_text(
            f"❌ {error_message}\nPlease try again with /ytb2transcript",
            reply_markup=ReplyKeyboardRemove()
        )

    def _get_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats."""
        try:
            parsed = urlparse(url)
            if parsed.netloc == 'youtu.be':
                return parsed.path[1:]
            if parsed.netloc in ('www.youtube.com', 'youtube.com'):
                if parsed.path == '/watch':
                    return parse_qs(parsed.query).get('v', [None])[0]
                if parsed.path.startswith(('/embed/', '/v/')):
                    return parsed.path.split('/')[2]
            return None
        except Exception:
            return None

    async def _get_video_title(self, video_id: str) -> str:
        """Fetch video title using oEmbed API."""
        try:
            response = requests.get(
                f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}",
                timeout=10
            )
            response.raise_for_status()
            return response.json()['title']
        except Exception as e:
            print(f"Error fetching video title: {str(e)}")
            return f"YouTube Video {video_id}"

    def _format_transcript(self, transcript: list, format_type: str, video_id: str, lang: str, title: str) -> str:
        """Format transcript with metadata and chosen format."""
        header = (
            f"Video Title: {title}\n"
            f"Video ID: {video_id}\n"
            f"Language: {lang}\n\n"
            "TRANSCRIPT:\n\n"
        )
        
        content = []
        for entry in transcript:
            if format_type == 'timestamp':
                mins, secs = divmod(int(entry['start']), 60)
                content.append(f"[{mins:02d}:{secs:02d}] {entry['text']}")
            else:
                content.append(entry['text'])
                
        return header + "\n".join(content)

# Singleton instance for handler
handler = YouTubeTranscriptHandler()