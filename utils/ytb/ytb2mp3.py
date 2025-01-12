import yt_dlp
import os
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
import requests
from PIL import Image
from io import BytesIO
import re
from pathlib import Path
import shutil
from typing import Optional, Tuple
from telegram import Update, Message
from telegram.ext import ContextTypes
import asyncio
import unicodedata

class YouTubeDownloader:
    def __init__(self, timeout: int = 300):
        self.download_dir = "youtube_media"
        self.timeout = timeout
        self.YOUTUBE_URL_REGEX = re.compile(
            r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)'
        )
        
        # Get the absolute path to the ffmpeg binary
        # current_dir = os.path.dirname(os.path.abspath(__file__))
        # self.ffmpeg_path = os.path.join(current_dir, 'bin', 'ffmpeg')
        
        # Make sure ffmpeg is installed on your environment
        self.ffmpeg_path = shutil.which('ffmpeg')
        
        # Path to the cookies file (update with the actual path)
        self.cookies_file = 'cookies.txt'  # Update this path

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename by removing/replacing invalid characters."""
        filename = unicodedata.normalize('NFKD', filename)
        invalid_chars = '<>:"/\\|?*#&;'
        for char in invalid_chars:
            filename = filename.replace(char, '')
        filename = filename.replace(' ', '_')
        filename = re.sub(r'_+', '_', filename)
        filename = filename.strip('_')
        filename = filename[:50]
        if not filename:
            filename = 'audio'
        return filename

    def _get_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from URL."""
        match = self.YOUTUBE_URL_REGEX.search(url)
        if match:
            return match.group(1)
        return None

    async def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[bytes]]:
        """
        Download and process YouTube video as MP3.
        Returns tuple of (file_path, error_message, caption, cover_art_bytes).
        """
        download_path = Path(self.download_dir)
        download_path.mkdir(parents=True, exist_ok=True)

        try:
            video_id = self._get_video_id(url)
            if not video_id:
                return None, "Invalid YouTube URL", None, None

            base_filename = f"youtube_{video_id}"
            output_template = str(download_path / base_filename)
            print(self.cookies_file)

            ydl_opts = {
                'quiet': False,
                'verbose': True,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320',
                }],
                'outtmpl': output_template,
                'no_warnings': True,
                'ffmpeg_location': self.ffmpeg_path,
                'quiet': True,
                'extract_flat': False,
                'noplaylist': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
                'referer': 'https://www.youtube.com/',
                'age_limit': 0,
                'cookies': self.cookies_file,  # Added cookies option
            }

            cover_art_bytes = None
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None, "Could not retrieve video information", None, None

                if 'thumbnails' in info and isinstance(info['thumbnails'], list):
                    thumbnail_url = info['thumbnails'][-1].get('url')
                    if thumbnail_url:
                        response = requests.get(thumbnail_url)
                        img = Image.open(BytesIO(response.content))
                        img_byte_arr = BytesIO()
                        img.convert('RGB').save(img_byte_arr, format='JPEG')
                        cover_art_bytes = img_byte_arr.getvalue()

                ydl.download([url])

                mp3_path = Path(f"{output_template}.mp3")
                if not mp3_path.exists():
                    return None, "MP3 file not created after download", None, None

                caption = f"🎵 *{info.get('title', 'Unknown Title')}*\n"
                caption += f"👤 {info.get('uploader', 'Unknown Artist')}\n"
                
                duration = info.get('duration')
                if duration:
                    minutes = int(duration) // 60
                    seconds = int(duration) % 60
                    caption += f"⏱ {minutes}:{seconds:02d}\n"

                view_count = info.get('view_count')
                if view_count is not None:
                    caption += f"👀 {view_count:,} views\n"

                like_count = info.get('like_count')
                if like_count is not None:
                    caption += f"❤️ {like_count:,} likes\n"

                try:
                    self._add_metadata(str(mp3_path), info)
                except Exception as e:
                    print(f"Warning: Could not add metadata: {str(e)}")

                return str(mp3_path), None, caption, cover_art_bytes

        except Exception as e:
            return None, f"Processing error: {str(e)}", None, None

    def _add_metadata(self, file_path: str, info: dict) -> None:
        """Add metadata and cover art to the MP3 file."""
        try:
            try:
                audio = EasyID3(file_path)
            except:
                audio = ID3()
                audio.save(file_path)
                audio = EasyID3(file_path)

            audio['title'] = info.get('title', 'Unknown Title')
            audio['artist'] = info.get('uploader', 'Unknown Artist')
            audio.save()

            try:
                if 'thumbnails' in info and isinstance(info['thumbnails'], list):
                    thumbnail_url = info['thumbnails'][-1].get('url')
                    if thumbnail_url:
                        audio = ID3(file_path)
                        response = requests.get(thumbnail_url)
                        img = Image.open(BytesIO(response.content))
                        
                        img_byte_arr = BytesIO()
                        img.convert('RGB').save(img_byte_arr, format='JPEG')
                        img_data = img_byte_arr.getvalue()

                        audio.add(APIC(
                            encoding=3,
                            mime='image/jpeg',
                            type=3,
                            desc='Cover',
                            data=img_data
                        ))
                        audio.save()
            except Exception as e:
                print(f"Warning: Could not add cover art: {str(e)}")
        except Exception as e:
            print(f"Warning: Could not add metadata: {str(e)}")

    async def _process_download(
        self,
        bot_instance: 'AIBot',
        update: Update,
        status_message: Message,
        url: str
    ) -> None:
        """Handle the download and sending process."""
        try:
            await bot_instance.retry_operation(
                status_message.edit_text,
                "⏳ Downloading and converting audio..."
            )
    
            file_path, error, caption, cover_art_bytes = await self.download_audio(url)
    
            if error:
                await bot_instance.retry_operation(
                    status_message.edit_text,
                    f"❌ {error}"
                )
                return
    
            if not file_path or not os.path.exists(file_path):
                await bot_instance.retry_operation(
                    status_message.edit_text,
                    "❌ No audio file was generated."
                )
                return
    
            await bot_instance.retry_operation(
                status_message.edit_text,
                "⏳ Uploading files..."
            )
    
            if cover_art_bytes:
                cover_bio = BytesIO(cover_art_bytes)
                cover_bio.name = 'cover.jpg'
                await bot_instance.retry_operation(
                    update.message.reply_photo,
                    photo=cover_bio,
                    caption="🖼 Album Cover"
                )
    
            with open(file_path, 'rb') as audio_file:
                await bot_instance.retry_operation(
                    update.message.reply_document,
                    document=audio_file,
                    caption=caption,
                    parse_mode='Markdown',
                    filename=os.path.basename(file_path)
                )
    
            await bot_instance.retry_operation(
                status_message.edit_text,
                "✅ Audio downloaded and sent successfully!"
            )
    
        except Exception as e:
            await bot_instance.retry_operation(
                status_message.edit_text,
                f"❌ Error processing audio: {str(e)}"
            )
    
        finally:
            try:
                shutil.rmtree(Path(self.download_dir), ignore_errors=True)
            except Exception as e:
                print(f"Error cleaning up files: {str(e)}")
                
    async def handle_youtube_command(
        self,
        bot_instance: 'AIBot',
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle the /ytb2mp3 command."""
        if not context.args:
            await bot_instance.retry_operation(
                update.message.reply_text,
                "Please provide a YouTube URL.\nUsage: /ytb2mp3 <url>"
            )
            return

        url = context.args[0]
        status_message = await bot_instance.retry_operation(
            update.message.reply_text,
            "⏳ Processing YouTube video..."
        )

        await self._process_download(bot_instance, update, status_message, url)
