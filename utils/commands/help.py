from telegram import Update
from telegram.ext import ContextTypes

async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command handler."""
    help_text = """
<b>Available Commands:</b>

- /start » Start the bot
- /help » Show help
- /clear » Clear history

<b>Capabilities:</b>

- Text chat with AI
- Image understanding
- Document processing
- Audio handling
- Chat history context
"""
    await self.retry_operation(update.message.reply_text, help_text, parse_mode='HTML')
