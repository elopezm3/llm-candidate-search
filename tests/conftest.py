"""Loaded by pytest before any test module: every test uses the in-memory span exporter, so no test ever sends traces
to the real Langfuse, whatever order the modules import the client in."""
import os

os.environ["LANGFUSE_TEST_EXPORT"] = "1"
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-test")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-test")
