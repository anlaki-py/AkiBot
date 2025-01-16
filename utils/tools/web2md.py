# web2md.py v1.0.4
import os
import re
import requests
import tempfile
from urllib.parse import urlparse, urljoin
from typing import Optional, Tuple
from telegram import Update, Message
from telegram.ext import ContextTypes
from pathlib import Path

class WebToMarkdownConverter:
    def __init__(self):
        self.TELEGRAM_MAX_LENGTH = 4096
        self.URL_REGEX = re.compile(
            r'(?:https?://)?(?:[\w-]+\.)+[\w-]+(?:/[\w-]+)*/?'
        )

    def _validate_url(self, url: str) -> Optional[str]:
        """Validate and format the URL."""
        if not url:
            return None
            
        # Add https:// if no protocol specified
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
            
        if not self.URL_REGEX.match(url):
            return None
            
        return url
        
    def _get_site_name(self, url: str) -> str:
        """Extract website name from URL for filename."""
        parsed = urlparse(url)
        site_name = parsed.netloc.split('.')[0]
        return site_name

    async def convert_to_markdown(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Convert webpage to markdown using jina.ai service.
        Returns tuple of (markdown_content, error_message, filename).
        """
        try:
            # Validate URL
            valid_url = self._validate_url(url)
            if not valid_url:
                return None, "Invalid URL format", None

            # Convert to jina.ai URL
            jina_url = f"https://r.jina.ai/{valid_url}"
            
            # Make request to jina.ai
            response = requests.get(jina_url)
            response.raise_for_status()
            
            # Get markdown content
            markdown_content = response.text
            
            # Generate filename
            site_name = self._get_site_name(url)
            filename = f"{site_name}.md"
            
            return markdown_content, None, filename

        except requests.RequestException as e:
            return None, f"Failed to fetch content: {str(e)}", None
        except Exception as e:
            return None, f"Error processing webpage: {str(e)}", None

    async def _send_preview(self, bot_instance: 'AIBot', update: Update, markdown_content: str) -> None:
        """Try to send preview with Markdown first, fall back to plain text if parsing fails."""
        try:
            # First attempt: with Markdown parsing
            await bot_instance.retry_operation(
                update.message.reply_text,
                f"📝 Preview:\n\n{markdown_content}",
                parse_mode='Markdown'
            )
        except Exception as markdown_error:
            if "Can't parse entities" in str(markdown_error):
                # Second attempt: without Markdown parsing
                await bot_instance.retry_operation(
                    update.message.reply_text,
                    f"📝 Preview (formatting disabled due to parsing errors):\n\n{markdown_content}",
                    parse_mode=None
                )
            else:
                # If it's not a parsing error, raise it
                raise

    async def _process_conversion(
        self,
        bot_instance: 'AIBot',
        update: Update,
        status_message: Message,
        url: str
    ) -> None:
        """Handle the conversion and sending process."""
        temp_path = None
        try:
            await bot_instance.retry_operation(
                status_message.edit_text,
                "⏳ Converting webpage to Markdown..."
            )
            
            markdown_content, error, filename = await self.convert_to_markdown(url)
            
            if error:
                await bot_instance.retry_operation(
                    status_message.edit_text,
                    f"❌ {error}"
                )
                return
                
            if not markdown_content:
                await bot_instance.retry_operation(
                    status_message.edit_text,
                    "❌ No content was generated."
                )
                return

            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as temp_file:
                temp_file.write(markdown_content)
                temp_path = temp_file.name

            # First send the file
            with open(temp_path, 'rb') as md_file:
                await bot_instance.retry_operation(
                    update.message.reply_document,
                    document=md_file,
                    caption=f"📄 Markdown version of {url}",
                    filename=filename
                )

            # Try to send preview if content is not too long
            if len(markdown_content) <= self.TELEGRAM_MAX_LENGTH:
                await self._send_preview(bot_instance, update, markdown_content)
            else:
                await bot_instance.retry_operation(
                    update.message.reply_text,
                    "⚠️ Content too long for preview (max 4096 characters)"
                )

            await bot_instance.retry_operation(
                status_message.edit_text,
                "✅ Webpage converted and sent successfully!"
            )

        except Exception as e:
            error_message = f"❌ Error during conversion: {str(e)}"
            if temp_path and os.path.exists(temp_path):
                error_message += "\nBut the file was generated - attempting to send..."
                try:
                    with open(temp_path, 'rb') as md_file:
                        await bot_instance.retry_operation(
                            update.message.reply_document,
                            document=md_file,
                            caption=f"📄 Markdown version of {url} (with errors)",
                            filename=filename
                        )
                    error_message += "\n✅ File sent successfully despite errors!"
                except Exception as file_error:
                    error_message += f"\n❌ Could not send file: {str(file_error)}"
            
            await bot_instance.retry_operation(
                status_message.edit_text,
                error_message
            )

        finally:
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    print(f"Error cleaning up temporary file: {str(e)}")

    async def handle_web2md_command(
        self,
        bot_instance: 'AIBot',
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle the /web2md command."""
        if not context.args:
            await bot_instance.retry_operation(
                update.message.reply_text,
                "Please provide a webpage URL.\nUsage: /web2md <url>"
            )
            return

        url = context.args[0]
        status_message = await bot_instance.retry_operation(
            update.message.reply_text,
            "⏳ Processing webpage..."
        )

        await self._process_conversion(bot_instance, update, status_message, url)
        