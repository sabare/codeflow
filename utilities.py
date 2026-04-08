from __future__ import annotations

import os

import dotenv

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

import logging

logger = logging.getLogger(__name__)

dotenv.load_dotenv()

SYSTEM_PROMPT = "You are a concise assistant that explains code clearly and briefly."


def call_llm(prompt: str) -> str:
    # return "Hello, world!"
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return ""

    model = os.getenv("OPENAI_MODEL", "gpt-5-nano")
    client = OpenAI(api_key=api_key)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        timeout=30,
    )
    content = completion.choices[0].message.content
    logger.info(f"Content: {content}")
    if not content:
        return ""
    return content
