# AkiBot (v1.0.2) - The Ultimate Telegram AI Assistant

This is a Telegram bot powered by the Gemini AI model, designed to interact with users through various media types and provide helpful responses.

## Functionality

The bot is capable of:

-   **Text Interaction:** Engaging in conversational text-based chats, maintaining context throughout the conversation.
-   **Image Understanding:** Processing images sent by users, allowing for vision-based queries.
-   **Document Analysis:** Reading and understanding text-based documents.
-   **Audio Processing:** Handling audio messages and files.
-   **Instagram Media Downloading:** Downloading photos and videos from Instagram links.
-   **YouTube to MP3 Conversion:** Converting YouTube videos to MP3 audio files.
-   **Webpage to Markdown Conversion:** Converting webpages to Markdown format.

## Features

-   **User Access Control:** Only allows access to users specified in the configuration.
-   **Chat History:** Maintains chat history for each user, allowing for contextual conversations.
-   **File Handling:** Processes various file types, including images, documents, and audio files.
-   **Instagram Downloader:** Downloads Instagram posts and reels, with options to send as compressed media or files.
-   **YouTube Downloader:** Downloads audio from YouTube videos as MP3 files, including metadata and cover art.
-   **Web to Markdown Converter:** Converts webpages into markdown format for easy reading and sharing.
-   **Error Handling:** Includes robust error handling and retry mechanisms for network issues and API rate limits.
-   **Configuration:** Utilizes a configuration file for easy customization of bot settings, including allowed users, AI model, and safety settings.
-   **User Logging:** Logs user data including first and last seen dates, chat type, and more.
-   **Config Editor:** Built-in web based configuration editor to modify the bot settings and system prompts.

## Commands

-   `/start`: Starts the bot and provides a welcome message.
-   `/help`: Displays a list of available commands and bot capabilities.
-   `/clear`: Clears the chat history for the current user.
-   `/insta <url>`: Downloads Instagram media from the provided URL as compressed media.
-   `/instaFile <url>`: Downloads Instagram media from the provided URL as uncompressed files.
-   `/ytb2mp3 <url>`: Downloads the audio from a YouTube video as an MP3 file.
-    `/web2md <url>`: Converts a webpage to a markdown file.

## Setup

1.  **Install Requirements:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **Environment Variables:**
    -   Set the `TELEGRAM_TOKEN_KEY` environment variable with your Telegram bot token.
    -   Set the `GEMINI_API_KEY` environment variable with your Gemini API key.
3. **First Time Run:**
    -   Execute the `run.sh` script:
        ```bash
        ./run.sh
        ```
        This will start the bot and the configuration editor, allowing you to set up the bot's configuration.
        The config editor will be available at `http://127.0.0.1:8080`.
        After configuring the bot, you can close the editor.
4.  **Run the Bot:**
    -   After the first time run, you can start the bot directly by running:
        ```bash
        python main.py
        ```
        
   
**Note:** After the first run using `run.sh`, you can run the bot directly with `python main.py`. The `run.sh` script is mainly for creating the initial config file.

## License

This project is licensed under my custom [license](LICENSE).
