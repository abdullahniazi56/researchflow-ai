"""Chat models. LLM_PROVIDER picks the main one; the other provider is
used as a fallback when its API key is set."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.globals import set_llm_cache
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "45"))

# identical prompts are served from disk (LLM_CACHE=off to disable)
if os.getenv("LLM_CACHE", "on").strip().lower() != "off":
    from langchain_community.cache import SQLiteCache

    CACHE_PATH = Path(__file__).resolve().parents[1] / ".llm_cache.db"
    set_llm_cache(SQLiteCache(database_path=str(CACHE_PATH)))


def _gemini():
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        api_key=os.getenv("GOOGLE_API_KEY"),
        # retrying a used-up quota is pointless, let the fallback answer
        max_retries=1,
        timeout=LLM_TIMEOUT,
    )


def _mistral():
    return ChatMistralAI(
        model=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
        api_key=os.getenv("MISTRAL_API_KEY"),
        max_retries=1,
        timeout=LLM_TIMEOUT,
    )


_builders = {
    "gemini": (_gemini, "GOOGLE_API_KEY"),
    "mistral": (_mistral, "MISTRAL_API_KEY"),
}

if PROVIDER not in _builders:
    raise ValueError(
        f"LLM_PROVIDER must be 'gemini' or 'mistral', got '{PROVIDER}'."
    )

backup_name = "mistral" if PROVIDER == "gemini" else "gemini"

primary_llm = _builders[PROVIDER][0]()

# Only use a backup model if its API key exists.
backup_llm = (
    _builders[backup_name][0]()
    if os.getenv(_builders[backup_name][1])
    else None
)

llm = (
    primary_llm.with_fallbacks([backup_llm])
    if backup_llm is not None
    else primary_llm
)


def structured_with_fallback(schema):
    """with_structured_output(schema), keeping the fallback model."""
    primary = primary_llm.with_structured_output(schema)

    if backup_llm is None:
        return primary

    return primary.with_fallbacks(
        [backup_llm.with_structured_output(schema)]
    )


def bind_tools_with_fallback(tools):
    """bind_tools(tools), keeping the fallback model."""
    primary = primary_llm.bind_tools(tools)

    if backup_llm is None:
        return primary

    return primary.with_fallbacks([backup_llm.bind_tools(tools)])
