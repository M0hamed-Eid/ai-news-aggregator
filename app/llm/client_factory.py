# app/llm/client_factory.py
#
# Single place that decides which LLM backend each agent talks to.
# Before this, every agent (DigestAgent [now EnrichmentAgent], CuratorAgent
# [deleted in M9 — ranking is now app.services.ranking_service, no LLM in
# the ranking path], EmailAgent) built its own Groq(api_key=...) client
# directly — meaning "switch to local" meant editing 3 files. Now it's one
# env var.
#
# task="simple"    -> EnrichmentAgent, EmailAgent (summaries, intros)
#                      can run locally via Ollama.
# task="reasoning" -> the 70B-class tier CuratorAgent used to use for
#                      ranking. Unused as of M9 (nothing calls this tier
#                      today) but kept defined — a future agent needing
#                      stronger reasoning (e.g. M11's grounded trend
#                      narrative) can reuse it rather than re-deriving a
#                      routing scheme.
# task="chat"       -> M14: AssistantAgent (RAG chat). Reuses the same
#                      70B model as "reasoning" — multi-source grounded
#                      synthesis needs the stronger tier, same reasoning
#                      as trend narrative, just a separate task name so a
#                      caller's intent ("interactive chat" vs "batch
#                      insight generation") stays explicit in call sites
#                      and future per-tier tuning (e.g. a chat-specific
#                      max_tokens) doesn't need to branch on task=="reasoning".

import os

from groq import Groq
from openai import OpenAI

from app.llm.groq_key_manager import GroqKeyManager, load_groq_keys

LOCAL_BASE_URL = "http://localhost:11434/v1"

# Groq model per task, for every task EXCEPT "simple" (which has its own
# local/Ollama branch below and otherwise falls through to the default at
# the bottom). Unmatched tasks (including "simple" on the Groq path) use
# llama-3.1-8b-instant, same as before this dict existed.
_GROQ_MODELS = {
    "reasoning": "llama-3.3-70b-versatile",
    "chat": "llama-3.3-70b-versatile",
}


def get_llm_client_and_model(task: str):
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if task == "simple" and provider == "local":
        client = OpenAI(
            base_url=LOCAL_BASE_URL,
            api_key="ollama",  # required by the SDK's constructor, ignored by Ollama itself
        )
        model = os.getenv("LOCAL_SIMPLE_MODEL", "llama3.1:8b")
        return client, model

    # Default path: Groq for everything, same as today. Uses GroqKeyManager
    # (app/llm/groq_key_manager.py) whenever GROQ_API_KEY_1/_2/... are
    # configured, transparently trying each in order on a rate-limit/quota/
    # auth failure — every call site here already just does
    # `self._client.chat.completions.create(...)`, which GroqKeyManager
    # also exposes, so no agent needed to change. Falls back to a single
    # plain Groq client when only ONE key is configured (either GROQ_API_KEY
    # alone, or exactly GROQ_API_KEY_1 with no _2/_3).
    #
    # Found live during a production QA pass (2026-08-10): this single-key
    # branch used to re-read os.environ["GROQ_API_KEY"] directly instead of
    # using keys[0] -- correct only when the BARE var happens to be set, but
    # both Render and the GitHub Actions pipeline are configured with ONLY
    # GROQ_API_KEY_1 (no bare GROQ_API_KEY), so os.environ["GROQ_API_KEY"]
    # silently resolved to "" there. Confirmed via a real 2h9m scheduled-
    # pipeline run: every single LLM call failed with
    # httpcore.LocalProtocolError: Illegal header value b'Bearer ' (an empty
    # key), meaning EnrichmentAgent/EmailAgent/TrendNarrativeAgent had been
    # silently producing zero output on every GitHub Actions run since
    # GROQ_API_KEY_1 replaced the bare key. keys[0] is always the correct
    # value here regardless of which env var name it came from.
    model = _GROQ_MODELS.get(task, "llama-3.1-8b-instant")
    keys = load_groq_keys()
    if not keys:
        raise ValueError("No Groq API key configured — set GROQ_API_KEY or GROQ_API_KEY_1.")
    if len(keys) > 1:
        return GroqKeyManager(keys), model
    client = Groq(api_key=keys[0])
    return client, model