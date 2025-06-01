from telegram import Update
from telegram.ext import ContextTypes

async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command handler."""
    help_text = """
<b>Available Commands</b>

• /start - Start the bot
• /help - Show this help message
• /clear - Clear chat history
• /think - Get detailed analysis
• /insta [link] - Download Instagram media
• /instaFile [link] - Download as file
• /ytb2mp3 [link] - Convert YouTube to MP3
• /ytb2transcript - Get video transcript
• /jailbreak - Load jailbreak prompt
• /web2md [url] - Convert webpage to Markdown
"""
    await self.retry_operation(update.message.reply_text, help_text, parse_mode='HTML')