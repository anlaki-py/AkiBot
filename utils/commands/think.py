# think.py v1.6.0
import tempfile
import requests
import json
import telegram
from telegram import Update
from telegram.ext import ContextTypes
from typing import Tuple, Optional

class ThinkCommand:
    THINK_MODEL = "gemini-2.0-flash-thinking-exp-1219"
    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
    SYSTEM_INSTRUCTIONS = """
    You are an expert problem solver. For every request:
    1. First provide detailed technical analysis
    2. Follow with a clean, implementation-ready solution
    3. Maintain strict separation between analysis and solution
    """

    async def handle_think_command(self, bot, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /think command with structured output"""
        try:
            prompt = self._get_prompt(context)
            raw_response = await self._get_api_response(bot, prompt)
            thought, solution = self._parse_response(raw_response)
            await self._send_structured_results(bot, update, thought, solution, raw_response)
        except Exception as e:
            await self._handle_error(update, e)

    def _get_prompt(self, context) -> str:
        """Extract and validate prompt from command arguments"""
        if not context.args:
            raise ValueError("Please provide a prompt after /think")
        return ' '.join(context.args)

    async def _get_api_response(self, bot, prompt: str) -> dict:
        """Get raw API response"""
        url = f"{self.API_URL}{self.THINK_MODEL}:generateContent?key={bot.config.gemini_api_key}"
        
        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": f"{self.SYSTEM_INSTRUCTIONS}\n\n{prompt}"}]
            }],
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
            parts = response['candidates'][0]['content']['parts']
            
            if len(parts) >= 2:
                return parts[0]['text'].strip(), parts[1]['text'].strip()
            
            if len(parts) == 1:
                full_text = parts[0]['text'].strip()
                code_start = full_text.find("```")
                if code_start != -1:
                    return full_text[:code_start].strip(), full_text[code_start:].strip()
                return full_text, "No distinct solution found"
            
            raise ValueError("Empty response from API")

        except (KeyError, IndexError) as e:
            raise ValueError("Invalid API response format") from e

    async def _send_structured_results(self, bot, update: Update, thought: str, solution: str, raw_response: dict) -> None:
        """Send results in specified order with proper formatting"""
        # 1. Send solution message first
        await self._send_solution_message(bot, update, solution)
        
        # 2. Send thought process as text file
        await self._send_text_file(bot, update, thought, "thought_process.txt")
        
        # 3. Send full response as markdown file
        await self._send_full_response_md(bot, update, raw_response, thought, solution)

    async def _send_solution_message(self, bot, update: Update, solution: str) -> None:
        """Send solution as plain text message with safe chunking"""
        BASE_PREFIX = "💡 Solution Part X:\n"  # Template for length calculation
        MAX_PREFIX_LENGTH = len(BASE_PREFIX) + 3  # Reserve space for 999 parts
        CHUNK_SIZE = 4096 - MAX_PREFIX_LENGTH  # Actual content space available
    
        if len(solution) > CHUNK_SIZE:
            chunks = [solution[i:i+CHUNK_SIZE] for i in range(0, len(solution), CHUNK_SIZE)]
            for i, chunk in enumerate(chunks, 1):
                prefix = f"💡 Solution Part {i}:\n"
                message = prefix + chunk
                
                # Final safety check
                if len(message) > 4096:
                    message = message[:4096]
                
                await bot.retry_operation(
                    update.message.reply_text,
                    message
                )
        else:
            await bot.retry_operation(
                update.message.reply_text,
                f"💡 Solution:\n{solution}"
            )
        
    async def _send_text_file(self, bot, update: Update, content: str, filename: str) -> None:
        """Send text content as a file"""
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as f:
            f.write(content)
            f.seek(0)
            await bot.retry_operation(
                update.message.reply_document,
                document=open(f.name, 'rb'),
                filename=filename
            )

    async def _send_full_response_md(self, bot, update: Update, raw_response: dict, thought: str, solution: str) -> None:
        """Create and send comprehensive markdown file"""
        md_content = self._generate_md_content(raw_response, thought, solution)
        
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False) as f:
            f.write(md_content)
            f.seek(0)
            await bot.retry_operation(
                update.message.reply_document,
                document=open(f.name, 'rb'),
                filename="full_response.md"
            )

    def _generate_md_content(self, raw_response: dict, thought: str, solution: str) -> str:
        """Generate formatted markdown content"""
        # Extract metadata
        model_version = raw_response.get("modelVersion", "N/A")
        usage = raw_response.get("usageMetadata", {})
        safety_ratings = raw_response.get("candidates", [{}])[0].get("safetyRatings", [])
        finish_reason = raw_response.get("candidates", [{}])[0].get("finishReason", "N/A")
        
        # Build markdown content
        md = [
            "# Full Response Documentation",
            f"**Model Version**: `{model_version}`",
            "## Usage Metrics",
            f"- Prompt Tokens: `{usage.get('promptTokenCount', 'N/A')}`",
            f"- Response Tokens: `{usage.get('candidatesTokenCount', 'N/A')}`",
            f"- Total Tokens: `{usage.get('totalTokenCount', 'N/A')}`",
            "## Safety Assessment",
        ]
        
        for rating in safety_ratings:
            md.append(f"- {rating.get('category', 'Unknown')}: `{rating.get('probability', 'N/A')}`")
        
        md.extend([
            "---",
            "## Thought Process",
            thought,
            "---",
            "## Final Solution",
            solution,
            "---",
            "## System Metadata",
            f"- Finish Reason: `{finish_reason}`",
            "## Raw Response Structure",
            "```json",
            json.dumps(raw_response, indent=2),
            "```"
        ])
        
        return "\n\n".join(md)

    async def _handle_error(self, update: Update, error: Exception) -> None:
        """Handle and report errors"""
        error_msg = str(error)[:4000]
        await update.message.reply_text(
            f"❌ Error:\n{error_msg}",
            parse_mode=None
        )

think_command = ThinkCommand()