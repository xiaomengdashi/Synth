from scripts.build_iphone_shortcut import build_shortcut


def test_shortcut_opens_share_page_with_encoded_input():
    shortcut = build_shortcut("https://x.kolane.top")

    assert shortcut["WFWorkflowName"] == "保存到 SynthAI"
    assert shortcut["WFWorkflowTypes"] == ["ActionExtension"]
    assert shortcut["WFWorkflowInputContentItemClasses"] == ["WFURLContentItem", "WFStringContentItem"]

    import_question = shortcut["WFWorkflowImportQuestions"][0]
    assert import_question["DefaultValue"] == "https://x.kolane.top"

    text_action = shortcut["WFWorkflowActions"][2]["WFWorkflowActionParameters"]["WFTextActionText"]
    assert text_action["Value"]["string"] == "\ufffc/share?text=\ufffc"
