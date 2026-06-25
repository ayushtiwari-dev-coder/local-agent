# FILE: engine/generate_with_retry.py
import time

def generate_with_retry(model, gemini_messages, max_attempts: int = 3) -> any:
    """
    Safely handles content generation with the Gemini model.
    Retries up to `max_attempts` times on transient network drops 
    or empty candidate lists before raising an exception.
    """
    for attempt in range(max_attempts):
        try:
            response = model.generate_content(gemini_messages)
            if response and response.candidates:
                return response
            
            # If candidates list is empty, wait before retrying
            if attempt < max_attempts - 1:
                time.sleep(1)
        except Exception as e:
            # If it is the last attempt, let the exception propagate
            if attempt == max_attempts - 1:
                raise e
            time.sleep(1)

    raise RuntimeError("No response candidates returned after multiple retries.")