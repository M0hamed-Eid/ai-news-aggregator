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

import os

from groq import Groq
from openai import OpenAI

LOCAL_BASE_URL = "http://localhost:11434/v1"


def get_llm_client_and_model(task: str):
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if task == "simple" and provider == "local":
        client = OpenAI(
            base_url=LOCAL_BASE_URL,
            api_key="ollama",  # required by the SDK's constructor, ignored by Ollama itself
        )
        model = os.getenv("LOCAL_SIMPLE_MODEL", "llama3.1:8b")
        return client, model

    # Default path: Groq for everything (both tasks), same as today
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    model = "llama-3.3-70b-versatile" if task == "reasoning" else "llama-3.1-8b-instant"
    return client, model