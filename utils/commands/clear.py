from telegram import Update
from telegram.ext import ContextTypes
import os

async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            print(f"Error deleting history: {str(e)}")
    
    await self.retry_operation(update.message.reply_text, "💬 Chat history cleared.", parse_mode='HTML')
