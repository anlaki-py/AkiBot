# ytb2transcript.py v1.0.0
import re
import os
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from typing import Optional, Dict, Any

class YouTubeTranscriptHandler:
    def __init__(self):
        self.states = {}

    async def handle_ytb2transcript_command(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Initiate transcript generation flow."""
        await update.message.reply_text("📝 Please send the YouTube video URL.")
        context.chat_data['transcript_state'] = 'awaiting_url'

    async def process_transcript_steps(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle multi-step transcript generation process."""
        user_id = update.effective_user.id
        state = context.chat_data.get('transcript_state')

        if state == 'awaiting_url':
            await self._process_url_input(bot, update, context)
        elif state == 'awaiting_language':
            await self._process_language_input(bot, update, context)
        elif state == 'awaiting_format':
            await self._process_format_input(bot, update, context)

    async def _process_url_input(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Extract video ID and available languages from URL."""
        url = update.message.text
        video_id = self._get_video_id(url)
        
        if not video_id:
            await update.message.reply_text("❌ Invalid YouTube URL. Please send a valid URL.")
            return

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            available_langs = [t.language_code for t in transcript_list]
            
            context.chat_data.update({
                'video_id': video_id,
                'available_langs': available_langs,
                'transcript_state': 'awaiting_language'
            })
            
            lang_list = "\n".join(available_langs)
            await update.message.reply_text(
                f"🌐 Available languages:\n{lang_list}\n"
                "Please reply with your preferred language code (e.g. 'en', 'de')."
            )
            
        except (TranscriptsDisabled, VideoUnavailable) as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
            context.chat_data.pop('transcript_state', None)

    async def _process_language_input(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle language selection and prompt for format."""
        lang = update.message.text.lower()
        available_langs = context.chat_data.get('available_langs', [])
        
        if lang not in available_langs:
            await update.message.reply_text("❌ Invalid language code. Please choose from available languages.")
            return
            
        context.chat_data.update({
            'language': lang,
            'transcript_state': 'awaiting_format'
        })
        
        await update.message.reply_text(
            "📝 Choose transcript format:\n"
            "1. With timestamps\n"
            "2. Plain text only\n"
            "Reply with '1' or '2'."
        )

    async def _process_format_input(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generate and send transcript based on user preferences."""
        choice = update.message.text
        if choice not in ['1', '2']:
            await update.message.reply_text("❌ Invalid choice. Please reply with '1' or '2'.")
            return
            
        format_type = 'timestamp' if choice == '1' else 'plain'
        video_id = context.chat_data['video_id']
        lang = context.chat_data['language']
        
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
            title = await self._get_video_title(video_id)
            file_content = self._format_transcript(transcript, format_type, video_id, lang, title)
            
            await update.message.reply_document(
                document=InputFile(io.StringIO(file_content), filename=f"{title[:50]}_transcript.txt"),
                caption=f"📄 {title}"
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error generating transcript: {str(e)}")
        finally:
            context.chat_data.pop('transcript_state', None)

    def _get_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats."""
        parsed = urlparse(url)
        if parsed.netloc == 'youtu.be':
            return parsed.path[1:]
        if parsed.netloc in ('www.youtube.com', 'youtube.com'):
            if parsed.path == '/watch':
                return parse_qs(parsed.query).get('v', [None])[0]
            if parsed.path.startswith('/embed/'):
                return parsed.path.split('/')[2]
            if parsed.path.startswith('/v/'):
                return parsed.path.split('/')[2]
        return None

    async def _get_video_title(self, video_id: str) -> str:
        """Fetch video title using oEmbed API."""
        try:
            response = requests.get(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}")
            return response.json()['title']
        except Exception:
            return "Untitled"

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
