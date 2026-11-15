import json


def to_json(report):
    return json.dumps(report, ensure_ascii=False, indent=2)
