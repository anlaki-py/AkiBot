# clear.py v1.1.0
from telegram import Update
from telegram.ext import ContextTypes
import os
import re
import shutil

async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear command handler for new directory structure."""
    user_id = str(update.effective_user.id)
    username = str(update.effective_user.username or "unknown")
    
    # Sanitize username to match directory naming
    sanitized_username = re.sub(r'[\\/*?:"<>|]', "", username.replace(" ", "_"))
    
    # Get user directory path
    user_dir = os.path.join("data", "users", f"{sanitized_username}_{user_id}")
    history_path = os.path.join(user_dir, "history", "chat_history.pkl")

    # Clear in-memory history
    if user_id in self.chat_history:
        del self.chat_history[user_id]
    
    # Clear persistent history
    try:
        if os.path.exists(history_path):
            os.remove(history_path)
            # Optional: Clean up empty directories
            if not os.listdir(os.path.dirname(history_path)):
                os.rmdir(os.path.dirname(history_path))
            if not os.listdir(user_dir):
                shutil.rmtree(user_dir)
    except Exception as e:
        print(f"Error clearing history: {str(e)}")
        await self.retry_operation(
            update.message.reply_text,
            "⚠️ Failed to fully clear history. Some data might remain.",
            parse_mode='HTML'
        )
        return

    await self.retry_operation(
        update.message.reply_text,
        "💬 Chat history cleared successfully.",
        parse_mode='HTML'
    )

# from telegram import Update
# from telegram.ext import ContextTypes
# import os

# async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # """Clear command handler."""
    # user_id = str(update.effective_user.id)
    # username = str(update.effective_user.username)
    
    # if user_id in self.chat_history:
        # del self.chat_history[user_id]
        
    # file_path = self.get_history_file_path(user_id, username)
    # if os.path.exists(file_path):
        # try:
            # os.remove(file_path)
        # except Exception as e:
            # print(f"Error deleting history: {str(e)}")
    
    # await self.retry_operation(update.message.reply_text, "💬 Chat history cleared.", parse_mode='HTML')
