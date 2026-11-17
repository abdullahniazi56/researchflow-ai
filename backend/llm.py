"""Chat model setup with automatic fallback.

LLM_PROVIDER in .env picks the main model ("gemini" or "mistral").
If the main model fails (for example the Gemini daily quota is used up),
LangChain automatically retries the same call on the other provider,
as long as its API key is set.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.globals import set_llm_cache
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

# Cache LLM responses on disk: asking the exact same prompt again
# (same question, same evidence) costs zero quota.
# Set LLM_CACHE=off in .env to disable it.
if os.getenv("LLM_CACHE", "on").strip().lower() != "off":
    from langchain_community.cache import SQLiteCache

    CACHE_PATH = Path(__file__).resolve().parents[1] / ".llm_cache.db"
    set_llm_cache(SQLiteCache(database_path=str(CACHE_PATH)))


def _gemini():
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        api_key=os.getenv("GOOGLE_API_KEY"),
        # A used-up daily quota won't come back by retrying,
        # so fail fast and let the fallback model answer.
        max_retries=1,
    )


def _mistral():
    return ChatMistralAI(
        model=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
        api_key=os.getenv("MISTRAL_API_KEY"),
        max_retries=1,
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
    """Like llm.with_structured_output(schema), with the fallback model.

    The model must return an object matching the Pydantic `schema`
    instead of free text, so we never have to parse text by hand.
    """
    primary = primary_llm.with_structured_output(schema)

    if backup_llm is None:
        return primary

    return primary.with_fallbacks(
        [backup_llm.with_structured_output(schema)]
    )


def bind_tools_with_fallback(tools):
    """Like llm.bind_tools(tools), but keeps the fallback model too."""
    primary = primary_llm.bind_tools(tools)

    if backup_llm is None:
        return primary

    return primary.with_fallbacks([backup_llm.bind_tools(tools)])


def gen_response(messages: str) -> str:
    response = llm.invoke(messages)
    return response.content
