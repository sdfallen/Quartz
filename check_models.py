from cerebras.cloud.sdk import Cerebras
import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("CEREBRAS_API_KEY")
print(f"Using key: {key[:15]}...")

client = Cerebras(api_key=key)

try:
    models = client.models.list()
    print("\nAvailable models on your account:")
    for m in models:
        print(f"  → {m.id}")
except Exception as e:
    print(f"Error: {e}")