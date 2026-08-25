import os

model_name = os.getenv("MODEL_NAME", "gemma-4-31b-it")
base_url = os.getenv("BASE_URL", "http://127.0.0.1:18000/v1/openai")
api_key = os.getenv("API_KEY", "")
