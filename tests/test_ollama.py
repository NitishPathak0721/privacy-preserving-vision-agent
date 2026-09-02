import requests

url = "http://localhost:11434/api/generate"

data = {
    "model": "llama3.2:3b",
    "prompt": "Explain browser automation in one simple sentence.",
    "stream": False
}

response = requests.post(url, json=data)

if response.status_code == 200:
    result = response.json()
    print("\nOllama Response:")
    print(result["response"])
else:
    print("Error:", response.status_code)
    print(response.text)
