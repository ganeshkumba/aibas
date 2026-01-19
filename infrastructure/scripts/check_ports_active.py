import requests

def check_port(port):
    url = f"http://localhost:{port}/api/generate"
    try:
        # Just check if it responds at all
        resp = requests.post(url, json={"model": "llama3.1", "prompt": "test", "stream": False}, timeout=1)
        print(f"Port {port}: SUCCESS ({resp.status_code})")
    except Exception as e:
        print(f"Port {port}: FAILED ({e})")

print("Checking potential AI ports...")
check_port(11434)
check_port(8000)
