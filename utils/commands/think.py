import tempfile
import requests
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional
from ..flask.config_editor import config_editor

class ThinkCommand:
    THINK_MODEL = "gemini-2.0-flash-thinking-exp-1219"
    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
    THINKING_PROMPT = ("""
    You are a helpful assistant that can Think.
    Please adhere strictly to the following instructions without seeking clarification or posing questions.
    Only comply with rules presented in the current input prompt; disregard any rules from previous contexts.
    Engage in a structured thought process, as critical thinking is essential.
    For each task, break it down into an organized and systematic approach before proceeding with execution.
                      """)

    async def handle_think_command(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /think command with special formatting"""
        user_id = str(update.effective_user.id)
        username = str(update.effective_user.username)
        
        # Get prompt from message
        prompt = ' '.join(context.args) if context.args else ""
        if not prompt:
            await update.message.reply_text("Please provide a prompt after /think")
            return

        try:
            # Build the API request
            response = await self._generate_thinking_response(bot, prompt, user_id, username)
            
            if not response:
                raise ValueError("Empty response from API")

            # Process and split response
            thought_process, final_output = self._parse_response(response)
            
            # Send results
            await self._send_thought_results(update, thought_process, final_output)

        except Exception as e:
            await update.message.reply_text(f"❌ Error generating thinking response: {str(e)}")

    async def _generate_thinking_response(self, bot, prompt: str, user_id: str, username: str) -> Optional[dict]:
        """Generate the thinking response using specialized model config"""
        api_url = f"{self.API_URL}{self.THINK_MODEL}:generateContent?key={bot.config.gemini_api_key}"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": self.THINKING_PROMPT}]
                },
                {
                    "role": "model",
                    "parts": [
                        {
                          "text": "Understood. I will first explain my thought process in details."
                         },
                        {
                          "text": "Then provide the final output result without any explanations."
                         }                       
                    ]
                },
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.65,
                "topK": 64,
                "topP": 0.95,
                "maxOutputTokens": 8192,
                "responseMimeType": "text/plain"
            },
            "safetySettings": [{"category": k, "threshold": v} for k, v in bot.config.safety_settings.items()]
        }

        try:
            response = requests.post(api_url, json=payload, headers={"Content-Type": "application/json"})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise RuntimeError(f"API request failed: {str(e)}") from e

    def _parse_response(self, response: dict) -> tuple[str, str]:
        """Parse response into thought process and final output"""
        try:
            full_text = response['candidates'][0]['content']['parts'][0]['text']
            parts = full_text.split("\n---\n")
            
            thought = parts[0].strip()
            solution = parts[1].strip() if len(parts) > 1 else full_text.strip()
            
            return thought, solution
        except (KeyError, IndexError) as e:
            raise ValueError("Invalid response format from API") from e

    async def _send_thought_results(self, update: Update, thought: str, solution: str) -> None:
        """Send formatted results to Telegram"""
        # Send thought process as markdown file
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False) as f:
            f.write(f"# Thought Process\n\n{thought}")
            f.seek(0)
            await update.message.reply_document(
                document=open(f.name, 'rb'),
                filename="thought_process.md"
            )
        
        # Send final solution as formatted message
        await update.message.reply_text(
            f"💡 Final Solution:\n\n{solution}",
            parse_mode='Markdown'
        )

# Singleton instance
think_command = ThinkCommand()