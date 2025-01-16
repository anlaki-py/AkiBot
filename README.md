# AkiBot (1.0.1) - The Ultimate Telegram AI Assistant

Welcome to AkiBot, a revolutionary Telegram bot that redefines the boundaries of AI interaction! Built with cutting-edge technology and designed for unparalleled user experience, AkiBot brings the power of Gemini AI to your fingertips through Telegram.

## ✨ What Makes AkiBot Special?

### 🚀 Lightning-Fast Performance
- Instant responses powered by Gemini's flash model
- Optimized message handling with retry mechanisms
- Seamless media processing and file management

### 🎯 Versatile Capabilities
- **Multi-Modal Intelligence**: Process text, images, documents, and voice messages effortlessly
- **Smart Link Detection**: Automatically identifies and processes Instagram posts and YouTube links
- **Media Downloads**: Built-in Instagram media downloader and YouTube to MP3 converter
- **Context-Aware**: Maintains conversation history for more meaningful interactions

### 🎨 User Experience
- Clean, intuitive interface
- Natural conversation flow
- Easy media sharing and processing
- Hassle-free document handling

### 🛡️ Advanced Features
- **Powerful Configuration**: Web-based configuration interface for easy customization
- **System Prompts**: Flexible prompt management through web interface
- **User Management**: Simple access control for sharing with friends
- **History Management**: Persistent chat history with easy clearing option

## 🌟 Why Choose AkiBot?

### Beyond Traditional Chatbots
Unlike conventional chatbots like ChatGPT, AkiBot offers:
- Seamless media integration
- Voice message processing
- Document analysis
- Instagram and YouTube integration
- Faster response times
- Customizable system behavior

### Easy Setup and Management
- Web-based configuration interface
- Simple user access management
- Flexible system prompt customization
- Zero-hassle deployment

## 🎮 Commands and Usage

### Core Commands
- `/start` - Begin your journey with AkiBot
- `/help` - Display available commands and features
- `/clear` - Reset conversation history

### Media Features
- `/insta [link]` - Download Instagram media (compressed)
- `/instaFile [link]` - Download Instagram media (uncompressed)
- `/ytb2mp3 [link]` - Convert YouTube videos to MP3

### Automatic Features
- Direct Instagram link processing
- YouTube link detection and conversion
- Image analysis and description
- Document understanding
- Voice message processing

## ⚙️ Configuration

AkiBot comes with a sleek web-based configuration interface that allows you to:
- Manage allowed users
- Customize AI model parameters
- Configure safety settings
- Edit system prompts
- Monitor bot performance

## 🚀 Getting Started

1. Add your Telegram token and Gemini API key to environment variables
2. Run the bot
3. Access the web configuration interface
4. Add allowed users
5. Start chatting!

## 🎯 Perfect For
- Personal AI assistant
- Group chat enhancement
- Media downloading and processing
- Document analysis
- Educational purposes
- Creative projects

Experience the future of AI interaction with AkiBot - where speed meets intelligence! 🚀

---

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.8 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Gemini API Key (from [Google AI Studio](https://makersuite.google.com/app/apikey))

### Quick Start Guide

1. **Clone and Setup Environment**
   ```bash
   # Clone the repository
   git clone https://github.com/anlaki-py/AkiBot
   cd AkiBot

   # Create and activate virtual environment
   python3 -m venv venv
   source venv/bin/activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Configure API Keys**
   ```bash
   # On Unix/macOS
   export TELEGRAM_TOKEN_KEY="your_telegram_token"
   export GEMINI_API_KEY="your_gemini_api_key"
   ```

3. **Launch the Bot**
   ```bash
   # Start the bot using the run script
   ./run.sh
   ```

### 🎛️ Configuration Interface

Upon first launch, AkiBot automatically:
- Creates the `config/config.json` file (if not present)
- Starts a web-based configuration interface at `http://127.0.0.1:8080`

#### Default Configuration
```json
{
    "allowed_users": [
        "YOUR_TELEGRAM_ID"
    ],
    "gemini_model": "gemini-2.0-flash-exp",
    "generation_config": {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "max_output_tokens": 1024,
        "response_mime_type": "text/plain"
    },
    "safety_settings": {
        "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
        "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
        "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE"
    },
    "system_prompt_file": "system/default.txt"
}
```

### 🔐 User Management

1. **Finding Your Telegram ID**
   - Start a chat with [@userinfobot](https://t.me/userinfobot) to get your Telegram ID
   - Or send a message to AkiBot - it will show your ID in the access denied message

2. **Adding Users**
   - Open the configuration interface at `http://127.0.0.1:8080`
   - Add Telegram IDs to the `allowed_users` section
   - Save changes - they take effect immediately

### 🔧 Advanced Configuration
The web interface allows you to:
- Modify AI model parameters
- Adjust safety settings
- Manage system prompts
- Configure response settings
- Monitor bot status

All changes are applied in real-time without requiring a bot restart!

## License

AkiBot is released under a custom non-commercial license:

- Free for personal and non-commercial use
- Modifications and distributions allowed (with attribution)
- Commercial use requires explicit permission
- Full source code access

For commercial licensing inquiries or full license details, please see the [LICENSE](LICENSE) file or contact the developer.
