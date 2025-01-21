# think.py v1.2.0
import tempfile
import requests
import re
import telegram
from telegram import Update
from telegram.ext import ContextTypes
from typing import Tuple, Optional
from pathlib import Path

class ThinkCommand:
    THINK_MODEL = "gemini-2.0-flash-thinking-exp-1219"
    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
    SOLUTION_DELIMITER = "||SOLUTION||"
    SYSTEM_INSTRUCTIONS = f"""
    You are an expert problem solver. For every request:
    1. Analyze the problem thoroughly with detailed reasoning
    2. Format your response EXACTLY as:
       [Markdown-formatted thought process]
       {SOLUTION_DELIMITER}
       [Final solution in appropriate format]
    
    Requirements:
    - Thought process must be in markdown
    - Final solution must be concise and implementation-ready
    - ALWAYS include the exact delimiter '{SOLUTION_DELIMITER}'
    - Never explain the solution after the delimiter
    """

    async def handle_think_command(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /think command with structured response parsing"""
        try:
            prompt = self._get_prompt(context)
            response = await self._get_api_response(bot, prompt)
            thought, solution = self._parse_response(response)
            await self._send_results(update, thought, solution)
        except Exception as e:
            await self._handle_error(update, e)

    def _get_prompt(self, context) -> str:
        """Extract and validate prompt from command arguments"""
        if not context.args:
            raise ValueError("Please provide a prompt after /think")
        return ' '.join(context.args)

    async def _get_api_response(self, bot, prompt: str) -> dict:
        """Get response from Gemini API with structured formatting"""
        url = f"{self.API_URL}{self.THINK_MODEL}:generateContent?key={bot.config.gemini_api_key}"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": self.SYSTEM_INSTRUCTIONS}]
                },
                {
                    "role": "model",
                    "parts": [{"text": f"Understood. I will use {self.SOLUTION_DELIMITER} to separate thoughts from solution."}]
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
            response = requests.post(url, json=payload, timeout=20)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API request failed: {str(e)}") from e

    def _parse_response(self, response: dict) -> Tuple[str, str]:
        """Extract thought process and solution from API response"""
        try:
            candidate = response['candidates'][0]
            parts = candidate['content']['parts']
            
            # Handle multi-part responses
            if len(parts) > 1:
                return parts[0]['text'], parts[1]['text']
                
            # Handle single-part responses with delimiter
            full_text = parts[0]['text']
            if self.SOLUTION_DELIMITER in full_text:
                thought, solution = full_text.split(self.SOLUTION_DELIMITER, 1)
                return thought.strip(), solution.strip()
                
            # Fallback pattern matching
            solution_match = re.search(r"(?:Final Solution:?|Implementation:)(.*)", full_text, re.DOTALL|re.IGNORECASE)
            if solution_match:
                return full_text[:solution_match.start()].strip(), solution_match.group(1).strip()
                
            # Ultimate fallback
            return full_text, "🚧 Solution format error - response missing delimiter"
            
        except (KeyError, IndexError) as e:
            raise ValueError("Invalid API response format") from e

    async def _send_results(self, update: Update, thought: str, solution: str) -> None:
        """Send formatted results with error handling"""
        # Send thought process as markdown file
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False) as f:
            f.write(f"# Thought Process\n\n{thought}")
            f.seek(0)
            await update.message.reply_document(
                document=open(f.name, 'rb'),
                filename="thought_process.md"
            )
        
        # Send solution with markdown fallback
        try:
            await self._send_solution(update, solution)
        except telegram.error.BadRequest as e:
            await self._send_solution(update, solution, use_markdown=False)

    async def _send_solution(self, update: Update, solution: str, use_markdown: bool = True) -> None:
        """Send solution with optional markdown formatting"""
        message = f"💡 **Final Solution**\n\n{solution}" if use_markdown else f"💡 FINAL SOLUTION\n\n{solution}"
        await update.message.reply_text(
            message,
            parse_mode='Markdown' if use_markdown else None
        )

    async def _handle_error(self, update: Update, error: Exception) -> None:
        """Handle and report errors gracefully"""
        error_msg = str(error).replace(self.SOLUTION_DELIMITER, '[DELIMITER]')
        await update.message.reply_text(
            f"❌ Error processing request:\n{error_msg}",
            parse_mode='Markdown'
        )

think_command = ThinkCommand()