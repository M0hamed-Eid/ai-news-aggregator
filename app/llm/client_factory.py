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

    # Default path: Groq for everything, same as today
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    model = _GROQ_MODELS.get(task, "llama-3.1-8b-instant")
    return client, model