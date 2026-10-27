import requests
import base64
import json
import os

# TODO: Replace with the actual URL and your hackathon API key
SAM_API_URL = os.getenv("SAM_API_URL")
API_KEY = os.getenv("API_KEY")

def test_sam_endpoint(image_path, noun_phrase):
    print(f"Testing SAM 3.1 Image Endpoint for: '{noun_phrase}' on {image_path}")
    
    # Encode image to base64
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Verifying the assumption: one noun phrase per call
    payload = {
        "image": encoded_string,
        "prompt": noun_phrase
    }

    try:
        response = requests.post(SAM_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        print("\n--- API Response ---")
        print(f"Boxes: {data.get('boxes')}")
        print(f"Scores: {data.get('scores')}")
        print("Masks returned:", len(data.get('masks', [])) > 0)
        return data
        
    except Exception as e:
        print(f"API Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(e.response.text)

if __name__ == "__main__":
    # Test this on one of the crops saved by your keyframer earlier!
    # test_sam_endpoint("data/frames/clip_desk_01/crop_120.jpg", "keys")
    pass