import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])

def consultar_groq(messages, temperature=0.3, max_tokens=1024):
    """Envía mensajes a Groq usando openai/gpt-oss-120b."""
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort="low"
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[Error] {str(e)}"

def chat_con_contexto(prompt_sistema, historial, pregunta_usuario,
                       temperature=0.3, max_tokens=1024):
    """Construye el contexto completo y consulta a Groq."""
    mensajes = [{"role": "system", "content": prompt_sistema}]
    mensajes.extend(historial)
    mensajes.append({"role": "user", "content": pregunta_usuario})
    return consultar_groq(mensajes, temperature, max_tokens)