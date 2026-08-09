import os
import asyncio
import logging

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


async def call_groq_with_retry(client, messages, model: str, temperature: float = 0.7, max_tokens: int = 1024, response_format = None, max_retries: int = 5, base_delay: float = 4.0):
    """
    Wrapper for Groq chat.completions.create that catches 429 rate limit errors 
    and retries with exponential backoff.
    """
    for attempt in range(max_retries + 1):
        try:
            params = {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                params["response_format"] = response_format
                
            return await client.chat.completions.create(**params)
        except Exception as exc:
            error_msg = str(exc)
            # Check if it is a rate limit error (429)
            is_rate_limit = "429" in error_msg or "rate_limit" in error_msg.lower() or "ResourceExhausted" in error_msg
            
            if is_rate_limit and attempt < max_retries:
                # Calculate delay with backoff
                sleep_time = base_delay * (2 ** attempt)
                logger.warning(
                    "Groq rate limit hit (429). Retrying in %.1f seconds... (Attempt %d/%d)",
                    sleep_time, attempt + 1, max_retries
                )
                await asyncio.sleep(sleep_time)
            else:
                # Out of retries or other error, raise the original exception
                raise exc
