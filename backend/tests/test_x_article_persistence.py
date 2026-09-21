from app.services import task_service


def test_local_summary_does_not_call_an_llm():
    result = task_service.build_local_summary("# 标题\n\n正文内容", "无正文")

    assert result == "标题 正文内容"
