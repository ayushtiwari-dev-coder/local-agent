# FILE: engine/generate_with_retry.py
import time

def generate_with_retry(
    request_fn, 
    is_quota_error_fn, 
    status_callback=None, 
    max_attempts: int = 3,
    base_delay: float = 2.0
) -> any:
    """
    Generic template to safely handle content generation and API requests for any LLM provider.
    Handles rate-limits (429s), transient exceptions, empty responses, and exponential backoff
    while updating the system console via status callbacks.
    """
    for attempt in range(max_attempts):
        try:
            # 1. Execute the actual provider request
            response = request_fn()
            
            if response:
                return response
                
            # Handle empty responses
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                if status_callback:
                    status_callback(
                        f"Encountered empty response. "
                        f"Retrying execution loop in {delay:.1f} seconds (Attempt {attempt + 1}/{max_attempts})..."
                    )
                time.sleep(delay)
                
        except Exception as e:
            # 2. Check if the error is a 429 rate limit
            is_quota_error = is_quota_error_fn(e)
            
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
                    response = request_response = f_run_attempt = request_fn()
                    if response:
                        return response
                    else:
                        raise RuntimeError("Daily quota limit has been reached. Stopping the request at this moment.")
                except Exception as retry_err:
                    raise RuntimeError("Daily quota limit has been reached. Stopping the request at this moment.") from retry_err
            
            # For other transient exceptions, check if we have reached the limit
            if attempt == max_attempts - 1:
                raise e
                
            delay = base_delay * (2 ** attempt)
            exc_str = str(e)
            if status_callback:
                status_callback(
                    f"Encountered an error inside this workflow: '{exc_str}'. "
                    f"Retrying execution loop in {delay:.1f} seconds (Attempt {attempt + 1}/{max_attempts})...."
                )
            time.sleep(delay)
            
    raise RuntimeError("No response returned after multiple retries.")