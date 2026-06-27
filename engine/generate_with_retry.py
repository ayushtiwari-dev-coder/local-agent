# FILE: engine/generate_with_retry.py
import time
from google import genai
from google.genai import types

def generate_with_retry(client, model_name, gemini_messages, config, max_attempts: int = 3, status_callback=None) -> any:
    """
    Safely handles content generation with the Gemini model.
    Retries up to `max_attempts` times using exponential backoff starting at a base delay of 2 seconds.
    
    If a 429 rate limit or quota exception is caught, it waits for a longer recovery fallback delay
    (3x base delay) and retries exactly once. If it fails a second time, it raises a clean exception.
    """
    base_delay = 2.0
    
    for attempt in range(max_attempts):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=gemini_messages,
                config=config
            )
            if response and response.candidates:
                return response
            
            # Handle empty response candidates
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                if status_callback:
                    status_callback(
                        f"Encountered empty response candidates. "
                        f"Retrying execution loop in {delay:.1f} seconds (Attempt {attempt + 1}/{max_attempts})..."
                    )
                time.sleep(delay)
                
        except Exception as e:
            exc_str = str(e)
            exc_class = type(e).__name__
            
            # Identify rate limit/quota errors (429)
            is_quota_error = (
                "ResourceExhausted" in exc_class or 
                "429" in exc_str or 
                "quota" in exc_str.lower()
            )
            
            if is_quota_error:
                quota_delay = base_delay * 3.0
                if status_callback:
                    status_callback(
                        f"Encountered a rate limit or quota error (429) inside this workflow. "
                        f"Waiting {quota_delay:.1f} seconds before initiating recovery retry..."
                    )
                time.sleep(quota_delay)
                
                # Attempt generation exactly once more
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=gemini_messages,
                        config=config
                    )
                    if response and response.candidates:
                        return response
                    else:
                        raise RuntimeError("Daily quota limit has been reached. Stopping the request at this moment.")
                except Exception as retry_err:
                    raise RuntimeError("Daily quota limit has been reached. Stopping the request at this moment.") from retry_err
            
            # For other transient exceptions, check if we have reached the limit
            if attempt == max_attempts - 1:
                raise e
            
            # Calculate exponential backoff delay (2s, 4s, 8s...)
            delay = base_delay * (2 ** attempt)
            if status_callback:
                status_callback(
                    f"Encountered an error inside this workflow: '{exc_str}'. "
                    f"Retrying execution loop in {delay:.1f} seconds (Attempt {attempt + 1}/{max_attempts})..."
                )
            time.sleep(delay)
            
    raise RuntimeError("No response candidates returned after multiple retries.")