# app/rag/__init__.py
#
# Retrieval-Augmented Generation building blocks for the AI assistant (M14).
# Phase A ships only the passage chunker; retrieval + generation land in later
# phases (see the architecture doc). Kept a package (not a single module) so the
# retriever/generator services can join it without churn.
