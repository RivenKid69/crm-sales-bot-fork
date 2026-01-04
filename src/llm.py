import requests

class OllamaLLM:
    def __init__(self, model: str = "qwen3:8b-fast"):
        self.model = model
        self.base_url = "http://localhost:11434"
    
    def generate(self, prompt: str) -> str:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "think": False  # Отключаем thinking mode для скорости
            },
            timeout=60
        )
        return response.json()["response"]


if __name__ == "__main__":
    llm = OllamaLLM()
    print(llm.generate("Привет! Ты работаешь?"))