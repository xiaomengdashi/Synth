from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_x_media_serves_assets_but_never_standalone_article_pages_or_json(tmp_path):
    from app.services.x_media import MediaFiles
    directory = tmp_path / 'x/123'
    directory.mkdir(parents=True)
    (directory / 'article.html').write_text('<h1>duplicate article</h1>')
    (directory / 'metadata.json').write_text('{"article": {}}')
    (directory / 'clip.mp4').write_bytes(b'video')
    app = FastAPI()
    app.mount('/media', MediaFiles(directory=tmp_path))
    with TestClient(app) as client:
        assert client.get('/media/x/123/article.html').status_code == 404
        assert client.get('/media/x/123/metadata.json').status_code == 404
        assert client.get('/media/x/123/clip.mp4').content == b'video'
