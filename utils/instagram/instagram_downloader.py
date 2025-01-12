import telegram
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import RetryAfter

from instaloader import Instaloader, Post, exceptions
import urllib.parse
import shutil
from pathlib import Path
from typing import Optional, Union, List
from datetime import datetime
import asyncio

class InstagramDownloader:
    def __init__(self, timeout: int = 300, max_group_size: int = 10):
        self.download_dir = "instagram_media"
        self.timeout = timeout  # Timeout in seconds (default 5 minutes)
        self.max_group_size = max_group_size  # Maximum number of media items per group

    def _format_post_info(self, post: Post) -> str:
        """Format post information into a readable caption."""
        upload_date = post.date_local.strftime("%Y-%m-%d %H:%M")
        
        caption = f"📱 Posted by [@{post.owner_username}](instagram.com/{post.owner_username})\n"
        caption += f"📅 {upload_date}\n"
        caption += f"❤️ {post.likes:,} likes\n"
        caption += f"💬 {post.comments:,} comments\n"
        
        if post.caption:
            caption += f"\n📝 Caption:\n{post.caption}\n"
            
        if post.location:
            caption += f"\n📍 Location: {post.location}\n"
            
        hashtags = " ".join(f"#{tag}" for tag in post.caption_hashtags) if post.caption_hashtags else ""
        if hashtags:
            caption += f"\n🏷 {hashtags}\n"
            
        return caption

    async def download_instagram_media(self, url: str) -> tuple[List[str], str, Optional[str]]:
        """
        Downloads Instagram media and returns paths to downloaded files, error message, and post caption.
        """
        def get_shortcode(url: str) -> Optional[str]:
            parsed_url = urllib.parse.urlparse(url)
            path = parsed_url.path
            if "/p/" in path:
                parts = path.split("/p/")[1].split("/")
                return parts[0].split("?")[0]
            elif "/reel/" in path:
                parts = path.split("/reel/")[1].split("/")
                return parts[0].split("?")[0]
            return None

        shortcode = get_shortcode(url)
        if not shortcode:
            return [], "Invalid Instagram post or reel link.", None

        download_path = Path(self.download_dir)
        download_path.mkdir(parents=True, exist_ok=True)

        loader = Instaloader(
            dirname_pattern=self.download_dir,
            filename_pattern="{shortcode}",
            download_comments=False,
            download_video_thumbnails=False,
            save_metadata=False
        )

        try:
            post = Post.from_shortcode(loader.context, shortcode)
            post_info = self._format_post_info(post)

            # Download the post
            loader.download_post(post, target=shortcode)

            # Get all downloaded files
            media_files = []
            for file in download_path.glob(f"{shortcode}*"):
                if file.suffix.lower() in {'.jpg', '.mp4', '.webp'}:
                    media_files.append(str(file))

            return media_files, "", post_info

        except exceptions.ProfileNotExistsException:
            return [], "Profile not found.", None
        except exceptions.PostPrivateError:
            return [], "This post is private.", None
        except exceptions.InvalidShortcodeException:
            return [], "Invalid shortcode.", None
        except exceptions.LoginRequiredException:
            return [], "Login required to access this post.", None
        except Exception as e:
            return [], f"An error occurred: {str(e)}", None

    def _split_media_files(self, media_files: List[str]) -> List[List[str]]:
        """Split media files into groups of maximum size."""
        return [media_files[i:i + self.max_group_size] 
                for i in range(0, len(media_files), self.max_group_size)]

    async def _send_media_group_with_timeout(
        self,
        bot_instance: 'AIBot',
        update: Update,
        media_group: List[Union[telegram.InputMediaPhoto, telegram.InputMediaVideo, telegram.InputMediaDocument]]
    ) -> None:
        """Send media group with timeout handling."""
        try:
            await asyncio.wait_for(
                bot_instance.retry_operation(update.message.reply_media_group, media_group),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            raise Exception(f"Operation timed out after {self.timeout} seconds")

    async def _process_media(
        self,
        bot_instance: 'AIBot',
        update: Update,
        status_message: telegram.Message,
        url: str,
        as_file: bool
    ) -> None:
        """Handle the media download and sending process."""
        try:
            # Download media
            media_files, error, post_info = await self.download_instagram_media(url)

            if error:
                await bot_instance.retry_operation(
                    status_message.edit_text,
                    f"❌ {error}"
                )
                return

            if not media_files:
                await bot_instance.retry_operation(
                    status_message.edit_text,
                    "❌ No media files found in the post."
                )
                return

            # Split media files into groups
            media_groups_files = self._split_media_files(media_files)
            total_groups = len(media_groups_files)

            for group_index, group_files in enumerate(media_groups_files, 1):
                # Update status message for multiple groups
                if total_groups > 1:
                    await bot_instance.retry_operation(
                        status_message.edit_text,
                        f"⏳ Sending media group {group_index}/{total_groups}..."
                    )

                # Prepare media group
                current_caption = post_info if group_index == 1 else None
                media_group = self._prepare_media_group(group_files, as_file, current_caption)

                # Send media group with timeout handling
                await self._send_media_group_with_timeout(bot_instance, update, media_group)

                # Add small delay between groups to prevent rate limiting
                if group_index < total_groups:
                    await asyncio.sleep(2)

            await bot_instance.retry_operation(
                status_message.edit_text,
                "✅ Media downloaded and sent successfully!"
            )

        except Exception as e:
            await bot_instance.retry_operation(
                status_message.edit_text,
                f"❌ Error sending media: {str(e)}"
            )

    def _prepare_media_group(
        self,
        media_files: List[str],
        as_file: bool,
        caption: Optional[str]
    ) -> List[Union[telegram.InputMediaPhoto, telegram.InputMediaVideo, telegram.InputMediaDocument]]:
        """Prepare media group based on file types and sending mode."""
        media_group = []
    
        for i, file_path in enumerate(media_files):
            file = open(file_path, 'rb')
            # Add caption only to the first media item
            current_caption = caption if i == 0 else ""
            
            # Common parameters for all media types
            media_params = {
                'media': file,
                'caption': current_caption,
                'parse_mode': 'Markdown'  # Add this line to enable Markdown parsing
            }
            
            if as_file:
                media_group.append(telegram.InputMediaDocument(**media_params))
            else:
                if file_path.lower().endswith(('.jpg', '.webp')):
                    media_group.append(telegram.InputMediaPhoto(**media_params))
                elif file_path.lower().endswith('.mp4'):
                    media_group.append(telegram.InputMediaVideo(**media_params))
    
        return media_group

    async def handle_instagram_command(
        self,
        bot_instance: 'AIBot',
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        as_file: bool = False
    ) -> None:
        """
        Generic handler for Instagram media downloads.
        """
        if not context.args:
            command = "/instaFile" if as_file else "/insta"
            await bot_instance.retry_operation(
                update.message.reply_text,
                f"Please provide an Instagram post/reel URL.\nUsage: {command} <url>"
            )
            return

        url = context.args[0]
        status_message = await bot_instance.retry_operation(
            update.message.reply_text,
            "⏳ Downloading media from Instagram..." + (" (sending as file)" if as_file else "")
        )

        try:
            await self._process_media(bot_instance, update, status_message, url, as_file)
        finally:
            # Clean up downloaded files
            try:
                shutil.rmtree(Path(self.download_dir), ignore_errors=True)
            except Exception as e:
                print(f"Error cleaning up files: {str(e)}")

    async def insta_command(self, bot_instance: 'AIBot', update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /insta command to download Instagram media as compressed media."""
        await self.handle_instagram_command(bot_instance, update, context, as_file=False)

    async def insta_file_command(self, bot_instance: 'AIBot', update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /instaFile command to download Instagram media as uncompressed files."""
        await self.handle_instagram_command(bot_instance, update, context, as_file=True)
        