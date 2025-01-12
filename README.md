# public-aki-tg-bot
**My telegram bot**

---

## config/config.json

```json
{
    "allowed_users": [
        "0123456789",
        "0987654321"
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

- allowed_users
    - Add the ID of users that will have access to use the bot

---

## Environmental variables

```
export TELEGRAM_TOKEN_KEY="<YOUR_TELEGRAM_TOKEN_KEY>"
export GEMINI_API_KEY="<YOUR_GEMINI_API_KEY>"
```
