"""Build an importable iPhone share shortcut; sign it with macOS `shortcuts sign`."""

import argparse
import plistlib
from pathlib import Path
from urllib.parse import urlsplit


def output_token(identifier, name):
    return {"Type": "ActionOutput", "OutputUUID": identifier, "OutputName": name}


def build_shortcut(base_url):
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use an HTTP(S) website address without credentials")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    site_id = "C2DA34A0-14D9-4471-823F-7DAF94049F67"
    encoded_id = "C8DF1DA1-06A9-48E9-B4B3-B18D292DC61A"
    target_id = "C6BEE78C-0C0E-4C45-AED0-2B351279633D"
    prefix = "\ufffc/share?text="
    text = {
        "WFSerializationType": "WFTextTokenString",
        "Value": {"string": prefix + "\ufffc", "attachmentsByRange": {
            "{0, 1}": output_token(site_id, "网站地址"),
            f"{{{len(prefix)}, 1}}": output_token(encoded_id, "URL 编码"),
        }},
    }
    return {
        "WFWorkflowName": "保存到 SynthAI",
        "WFWorkflowClientVersion": "3036.0.4.2",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4251333119, "WFWorkflowIconGlyphNumber": 59511},
        "WFWorkflowTypes": ["ActionExtension"],
        "WFWorkflowInputContentItemClasses": ["WFURLContentItem", "WFStringContentItem"],
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowImportQuestions": [{
            "ActionIndex": 0, "Category": "Parameter", "ParameterKey": "WFTextActionText",
            "Text": "填写 iPhone 能打开的 SynthAI 网站地址，不含末尾斜杠。例如 http://192.168.1.10:5173。", "DefaultValue": origin,
        }],
        "WFWorkflowActions": [
            {"WFWorkflowActionIdentifier": "is.workflow.actions.gettext", "WFWorkflowActionParameters": {"WFTextActionText": origin, "UUID": site_id}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.urlencode", "WFWorkflowActionParameters": {
                "WFEncodeMode": "Encode", "UUID": encoded_id,
                "WFInput": {"WFSerializationType": "WFTextTokenAttachment", "Value": {"Type": "ExtensionInput"}},
            }},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.gettext", "WFWorkflowActionParameters": {"WFTextActionText": text, "UUID": target_id}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.openurl", "WFWorkflowActionParameters": {
                "WFInput": {"WFSerializationType": "WFTextTokenAttachment", "Value": output_token(target_id, "文本")},
            }},
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(plistlib.dumps(build_shortcut(args.base_url), fmt=plistlib.FMT_XML, sort_keys=False))
    print(args.output)
