import hashlib
import json
import sqlite3
import os

# Note: You need to verify SAM 3.1 API facts (rate limits, prompt format) from the hackathon docs.
# This wrapper assumes the image endpoint takes an image and a single noun phrase.

DB_PATH = "data/spatialtrace.db"

def get_cache_key(endpoint, payload):
    # Hash the endpoint and payload to create a unique cache key
    cache_string = f"{endpoint}_{json.dumps(payload, sort_keys=True)}"
    return hashlib.md5(cache_string.encode('utf-8')).hexdigest()

def check_cache(cache_key):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT response_json FROM api_cache WHERE key = ?", (cache_key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None

def save_to_cache(cache_key, response_data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO api_cache (key, response_json) VALUES (?, ?)",
        (cache_key, json.dumps(response_data))
    )
    conn.commit()
    conn.close()

async def call_sam_image_endpoint(image_path, noun_phrase):
    """
    Calls SAM 3.1 Image Endpoint with one noun phrase per call.
    """
    endpoint = "sam_3.1_image"
    payload = {"image_path": image_path, "prompt": noun_phrase}
    cache_key = get_cache_key(endpoint, payload)
    
    # Disk cache on every API call[cite: 1]
    cached_response = check_cache(cache_key)
    if cached_response:
        print(f"Cache hit for '{noun_phrase}' on {image_path}")
        return cached_response

    print(f"Cache miss. Calling SAM API for '{noun_phrase}'...")
    # TODO: Replace with actual SAM 3.1 HTTP POST request using your hackathon API key
    # Mock response for now
    mock_response = {
        "masks": ["path/to/mock_mask.png"], 
        "boxes": [[100, 100, 200, 200]], 
        "scores": [0.95]
    }
    
    save_to_cache(cache_key, mock_response)
    return mock_response