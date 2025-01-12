# public-aki-tg-bot

---

**My telegram bot**

---

## Run the bot

**Create virtual environment**

```bash
python3 -m venv venv

```

**Enter virtual environment**

```bash
. venv/bin/activate
```

**Install requirements**

```bash
pip install -r requirements.txt
```

**Set environmental variables**

```bash
export TELEGRAM_TOKEN_KEY="<YOUR_TELEGRAM_TOKEN_KEY>"
export GEMINI_API_KEY="<YOUR_GEMINI_API_KEY>"
```

**Run the bot**

```bash
. run.sh
```

> Flask web app will start at http://127.0.0.1:8080 and it's a config editor for `config/config.json`

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

- `allowed_users`
    - Add the ID of users that will have access to use the bot

---

## License

This project is licensed under a custom non-commercial license.

- You are free to use, modify, and distribute this project for non-commercial purposes.
- For commercial use, please contact me to discuss licensing terms.
- Proper attribution is required if you modify and share this work.

For the full license text, see the [LICENSE](LICENSE) file.
