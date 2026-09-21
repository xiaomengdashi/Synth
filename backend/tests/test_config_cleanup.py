from app.routers.config import _public_config


def test_public_config_drops_legacy_x_article_api_key():
    result = _public_config(
        {
            "apiKey": "llm-key",
            "baseUrl": "https://example.com/v1",
            "modelName": "model",
            "xArticleApiKey": "legacy-key",
        }
    )

    assert result["apiKey"] == "llm-key"
    assert "xArticleApiKey" not in result
