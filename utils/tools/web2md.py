# web2md.py v1.0.0
import requests
from typing import List, Optional
import urllib.parse

class Web2MarkdownConverter:
    """Class to handle website to markdown conversion using Jina's service."""
    
    def __init__(self):
        self.jina_base_url = "https://r.jina.ai/"
        self.chunk_size = 4000  # Slightly less than Telegram's 4096 limit for safety
        
    def _validate_url(self, url: str) -> bool:
        """Validate if the URL is properly formatted."""
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
            
    def _chunk_markdown(self, markdown_text: str) -> List[str]:
        """Split markdown text into chunks that fit within Telegram's message limit."""
        chunks = []
        current_chunk = ""
        
        # Split by paragraphs to avoid breaking mid-sentence
        paragraphs = markdown_text.split('\n\n')
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed chunk size, start a new chunk
            if len(current_chunk) + len(paragraph) + 2 > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + '\n\n'
            else:
                current_chunk += paragraph + '\n\n'
                
        # Add the last chunk if there's anything left
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks
        
    async def convert_url_to_markdown(self, url: str) -> Optional[List[str]]:
        """
        Convert a webpage to markdown format using Jina's service.
        
        Args:
            url: The URL of the webpage to convert
            
        Returns:
            List of markdown chunks if successful, None if failed
            
        Raises:
            ValueError: If URL is invalid
            RequestError: If conversion fails
        """
        if not self._validate_url(url):
            raise ValueError("Invalid URL format")
            
        # Construct Jina URL
        encoded_url = urllib.parse.quote(url, safe='')
        jina_url = f"{self.jina_base_url}{encoded_url}"
        
        try:
            # Get markdown from Jina
            response = requests.get(jina_url)
            response.raise_for_status()
            
            # Split into chunks and return
            markdown_chunks = self._chunk_markdown(response.text)
            return markdown_chunks
            
        except requests.RequestException as e:
            raise RequestError(f"Failed to convert webpage: {str(e)}")

class RequestError(Exception):
    """Custom exception for request-related errors."""
    pass