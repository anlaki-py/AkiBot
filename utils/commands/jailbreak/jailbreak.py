# jailbreak.py v1.0.0

import os
import telegram
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

class JailbreakHandler:
    JAILBREAK_DIR = "system/jailbreak"

    @classmethod
    async def list_jailbreaks(cls, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        List available jailbreak prompt files.
        
        Args:
            bot: The AIBot instance
            update: Telegram update object
            context: Telegram context object
        """
        try:
            # Ensure jailbreak directory exists
            os.makedirs(cls.JAILBREAK_DIR, exist_ok=True)
            
            # Get list of jailbreak files
            jailbreak_files = [f for f in os.listdir(cls.JAILBREAK_DIR) 
                               if f.endswith('.txt')]
            
            if not jailbreak_files:
                await bot.send_response_with_toggle(
                    update, 
                    context, 
                    "No jailbreak prompts found. Please add .txt files to the jailbreak directory."
                )
                return
            
            # Create inline keyboard with jailbreak files
            keyboard = []
            for file in jailbreak_files:
                callback_data = f"jailbreak_{file}"
                keyboard.append([InlineKeyboardButton(file, callback_data=callback_data)])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await bot.send_response_with_toggle(
                update, 
                context, 
                "Select a jailbreak prompt:", 
                reply_markup=reply_markup
            )
        
        except Exception as e:
            await bot.send_response_with_toggle(
                update, 
                context, 
                f"Error listing jailbreaks: {str(e)}"
            )

    @classmethod
    async def handle_jailbreak_selection(cls, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle the selection of a jailbreak prompt.
        """
        query = update.callback_query
        await query.answer()
        
        try:
            # Extract filename from callback data
            filename = query.data.split('_', 1)[1]
            filepath = os.path.join(cls.JAILBREAK_DIR, filename)
            
            # Read jailbreak prompt
            with open(filepath, 'r', encoding='utf-8') as f:
                jailbreak_prompt = f.read().strip()
            
            # Get user information
            user_id = str(query.from_user.id)
            username = str(query.from_user.username)
            
            # Send jailbreak prompt to the chat
            chat = bot.chat_history[user_id]
            await chat.send_message_async(jailbreak_prompt, role="system")
            
            # Save chat history
            await bot.save_chat_history(user_id, username)
            
            # Confirm prompt selection
            await bot.send_response_with_toggle(
                update,  # Pass the entire update object
                context, 
                f"✅ Jailbreak prompt '{filename}' activated."
            )
        
        except FileNotFoundError:
            await bot.send_response_with_toggle(
                update, 
                context, 
                "Jailbreak file not found."
            )
        except Exception as e:
            await bot.send_response_with_toggle(
                update, 
                context, 
                f"Error applying jailbreak: {str(e)}"
            )

# Command handler function to be imported in main script
async def jailbreak_command(bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Main command handler for /jailbreak command.
    
    Args:
        bot: The AIBot instance
        update: Telegram update object
        context: Telegram context object
    """
    # Ensure user has a chat history
    user_id = str(update.effective_user.id)
    username = str(update.effective_user.username)
    await bot.initialize_chat(user_id, username)
    
    await JailbreakHandler.list_jailbreaks(bot, update, context)

# Callback handler for jailbreak selection
async def jailbreak_callback_handler(bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback handler for jailbreak prompt selection.
    
    Args:
        bot: The AIBot instance
        update: Telegram update object
        context: Telegram context object
    """
    await JailbreakHandler.handle_jailbreak_selection(bot, update, context)