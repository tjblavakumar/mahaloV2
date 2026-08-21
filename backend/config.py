import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    """Environment settings for MAHALO."""

    PROJECT_ROOT = Path(__file__).resolve().parent.parent

    MAIN_API_PORT = int(os.getenv("MAIN_API_PORT", "8000"))
    JIRA_API_PORT = int(os.getenv("JIRA_API_PORT", "5001"))
    SERVICENOW_API_PORT = int(os.getenv("SERVICENOW_API_PORT", "5002"))
    SPLUNK_API_PORT = int(os.getenv("SPLUNK_API_PORT", "5003"))
    JIRA_MCP_PORT = int(os.getenv("JIRA_MCP_PORT", "6001"))
    SERVICENOW_MCP_PORT = int(os.getenv("SERVICENOW_MCP_PORT", "6002"))
    SPLUNK_MCP_PORT = int(os.getenv("SPLUNK_MCP_PORT", "6003"))
    FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "3000"))
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mahalo.db")

    # These are alternative names for the same configured provider key.
    ONE_MIN_AI_API_KEY = (
        os.getenv("ONE_MIN_AI_API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("OPEN_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    )
    ONE_MIN_AI_BASE_URL = os.getenv("ONE_MIN_AI_BASE_URL") or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.1min.ai/v1"
    LITELLM_MODEL = os.getenv("LITELLM_MODEL", "gpt-4o-mini")

    # Proxy configuration (automatically reads HTTP_PROXY, HTTPS_PROXY, NO_PROXY from environment)
    # These settings ensure httpx respects system proxy configuration
    HTTP_PROXY = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    HTTPS_PROXY = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    NO_PROXY = os.getenv("NO_PROXY") or os.getenv("no_proxy", "localhost,127.0.0.1")


settings = Settings()


def get_llm_config() -> dict:
    """Build LiteLLM-compatible config for provider clients."""
    return {
        "model": settings.LITELLM_MODEL,
        "api_key": settings.ONE_MIN_AI_API_KEY,
        "base_url": settings.ONE_MIN_AI_BASE_URL,
    }


def get_httpx_client_config() -> dict:
    """Build httpx client config with proxy support.
    
    Returns a dict of kwargs to pass to httpx.AsyncClient() or httpx.Client().
    When trust_env=True, httpx will automatically use HTTP_PROXY, HTTPS_PROXY, 
    and NO_PROXY environment variables.
    """
    config = {
        "timeout": 10.0,
        "trust_env": True,  # Enable proxy detection from environment
    }
    
    # Optionally, you can explicitly set proxies if needed
    # This is useful for debugging or overriding environment variables
    proxies = {}
    if settings.HTTP_PROXY:
        proxies["http://"] = settings.HTTP_PROXY
    if settings.HTTPS_PROXY:
        proxies["https://"] = settings.HTTPS_PROXY
    
    if proxies:
        config["proxies"] = proxies
    
    return config
