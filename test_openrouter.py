import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_openrouter():
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        print("❌ OPENROUTER_API_KEY not found in .env")
        return

    print(f"Testing OpenRouter API with key: {api_key[:5]}...{api_key[-5:]}")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/coinbase-trading-bot",
        "X-Title": "Coinbase Trading Bot Test"
    }
    
    payload = {
        "model": "x-ai/grok-4.1-fast",
        "messages": [
            {"role": "user", "content": "Say 'Hello, World!' if you can hear me."}
        ],
        "max_tokens": 50
    }
    
    try:
        print("Sending request...")
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            print("\n✅ Success! Response from Grok:")
            print("-" * 40)
            print(content)
            print("-" * 40)
        else:
            print(f"\n❌ API Error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"\n❌ Connection Error: {e}")

if __name__ == "__main__":
    test_openrouter()
