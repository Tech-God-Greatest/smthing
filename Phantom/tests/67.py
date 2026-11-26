from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

messages = [
    {
        "role": "system",
        "content": "You are a helpful AI assistant."
    }
]

print("Ollama AI ready. Type 'exit' to quit.\n")

while True:
    user_input = input("You: ")

    if user_input.lower() == "exit":
        break

    messages.append({
        "role": "user",
        "content": user_input
    })

    response = client.chat.completions.create(
        model="qwen3:8b",
        messages=messages
    )

    reply = response.choices[0].message.content

    print(f"Ollama: {reply}\n")

    messages.append({
        "role": "assistant",
        "content": reply
    })