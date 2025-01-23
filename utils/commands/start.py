from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
import os
import json
import re
import shutil

async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler with user logging functionality."""
    user = update.effective_user
    username = str(user.username) if user.username else f"user_{user.id}"
    user_id = user.id
    
    # Sanitize username for filesystem safety
    sanitized_username = re.sub(r'[\\/*?:"<>|]', "", username.replace(" ", "_"))
    
    # Create user directory structure
    user_root = os.path.join("data", "users", f"{sanitized_username}_{user_id}")
    info_dir = os.path.join(user_root, "info")
    history_dir = os.path.join(user_root, "history")
    
    os.makedirs(info_dir, exist_ok=True)
    os.makedirs(history_dir, exist_ok=True)

    # Prepare user data
    user_data = {
        'user_id': user_id,
        'username': username,
        'sanitized_username': sanitized_username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'is_bot': user.is_bot,
        'language_code': user.language_code,
        'can_join_groups': user.can_join_groups,
        'can_read_all_group_messages': user.can_read_all_group_messages,
        'supports_inline_queries': user.supports_inline_queries,
        'first_seen': datetime.now().isoformat(),
        'chat_id': update.message.chat_id,
        'chat_type': update.message.chat.type,
        'directory_structure': {
            'root': user_root,
            'info': info_dir,
            'history': history_dir
        }
    }

    # File paths
    user_info_file = os.path.join(info_dir, "user_info.json")
    start_log_file = os.path.join(info_dir, "start.log")

    try:
        # Handle existing user data
        existing_data = {}
        if os.path.exists(user_info_file):
            try:
                with open(user_info_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        existing_data = json.loads(content)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                # Backup corrupted file
                backup_name = f"{user_info_file}.bak.{int(datetime.now().timestamp())}"
                shutil.copyfile(user_info_file, backup_name)

        # Preserve first seen timestamp
        if existing_data and 'first_seen' in existing_data:
            user_data['first_seen'] = existing_data['first_seen']
            
        # Update last seen
        user_data['last_seen'] = datetime.now().isoformat()

        # Save user info
        with open(user_info_file, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, indent=4, ensure_ascii=False)

        # Log start event
        with open(start_log_file, 'a') as f:
            f.write(f"{datetime.now().isoformat()} - Start command invoked\n")

    except Exception as e:
        print(f"Error handling user data: {str(e)}")
        # Create error log in user directory
        error_log = os.path.join(user_root, "error.log")
        with open(error_log, 'a') as f:
            f.write(f"{datetime.now().isoformat()} - {str(e)}\n")

    # Send welcome message
    await self.retry_operation(
        update.message.reply_text,
        f"""Welcome {user.first_name}!\nI'm your AkiBot. Send me text, images, documents or audio and I will respond.\nUse /help for more info."""
    )

# from datetime import datetime
# from telegram import Update
# from telegram.ext import ContextTypes
# import os
# import json

# async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # """Start command handler with user logging functionality."""
    # user = update.effective_user
    # username = str(user.username) if user.username else f"user_{user.id}"
    # user_id = user.id

    # # Create user data directory
    # os.makedirs('data/users', exist_ok=True)

    # # Prepare user data
    # user_data = {
        # 'user_id': user_id,
        # 'username': username,
        # 'first_name': user.first_name,
        # 'last_name': user.last_name,
        # 'is_bot': user.is_bot,
        # 'language_code': user.language_code,
        # 'can_join_groups': user.can_join_groups,
        # 'can_read_all_group_messages': user.can_read_all_group_messages,
        # 'supports_inline_queries': user.supports_inline_queries,
        # 'first_seen': datetime.now().isoformat(),
        # 'chat_id': update.message.chat_id,
        # 'chat_type': update.message.chat.type,
    # }

    # # Save user data
    # filename = f'data/users/{username}_{user_id}.json'
    # try:
        # existing_data = {}
        # if os.path.exists(filename):
            # try:
                # with open(filename, 'r', encoding='utf-8') as f:
                    # content = f.read().strip()
                    # if content:
                        # existing_data = json.loads(content)
            # except (json.JSONDecodeError, UnicodeDecodeError) as e:
                # if os.path.exists(filename):
                    # backup_name = f"{filename}.bak.{int(datetime.now().timestamp())}"
                    # os.rename(filename, backup_name)

        # if existing_data and 'first_seen' in existing_data:
            # user_data['first_seen'] = existing_data['first_seen']
        # user_data['last_seen'] = datetime.now().isoformat()

        # with open(filename, 'w', encoding='utf-8') as f:
            # json.dump(user_data, f, indent=4, ensure_ascii=False)

    # except Exception as e:
        # print(f"Error handling user data: {str(e)}")

    # # Send welcome message
    # await self.retry_operation(
        # update.message.reply_text,
        # f"""Welcome {user.first_name} !\nI'm your AkiBot. Send me text, images, documents or audio and I will respond.\nUse /help for more info."""
    # )
