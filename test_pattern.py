from typing import Any

def _format_list_advisory(value: list[Any]) -> str:
    return ", ".join(str(v) for v in value)

def _format_dict_advisory(value: dict[str, Any]) -> str:
    return str(value)

def _format_advisory_value(value: Any) -> str:
    match value:
        case list():
            return _format_list_advisory(value)
        case dict():
            return _format_dict_advisory(value)
        case str():
            return value
        case _:
            return str(value)

def _get_fallback_narrative(context: Any) -> str:
    match context:
        case str():
            return context
        case _:
            return "Fallback"

print(_format_advisory_value([1,2,3]))
print(_get_fallback_narrative(123))
