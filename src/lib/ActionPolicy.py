"""Conservative intent and confirmation rules for consequential Elite actions."""
import re
from time import monotonic, sleep



def explicit_chat_intent(text: str) -> bool:
    text = text.casefold().strip()
    # Saying something *to TARS* is not asking it to type into Elite.
    if re.search(r"\b(tell|send|say|answer)\s+(me|myself)\b", text):
        return False
    return bool(
        re.search(r"^(?:tars[,:]?\s+)?(?:please\s+|(?:could|would|can|will)\s+you\s+)?(?:send|post|type|tell|message)\b", text)
        and (re.search(r"\b(chat|channel)\b", text)
             or re.search(r"\bsend\s+\S+.*\b(message|this|that)\b", text))
    )


def validate_chat_message(obj: dict, commander_name: str, intent: str) -> None:
    if not explicit_chat_intent(intent):
        raise ValueError("Not sent: explicit intent to send a message in Elite chat is required.")
    if not isinstance(obj, dict) or not isinstance(obj.get("message"), str) or not obj["message"].strip():
        raise ValueError("Not sent: a non-empty message is required.")
    if any(c in obj["message"] for c in "\r\n") or obj["message"].lstrip().startswith("/"):
        raise ValueError("Not sent: chat commands and multiline messages are not supported.")
    channel = str(obj.get("channel", "")).casefold()
    if channel not in ("local", "system", "wing", "squadron", "commander"):
        raise ValueError("Not sent: select an explicit Elite chat channel.")
    if channel != "commander" and not re.search(r"\b" + channel + r"\b", intent.casefold()):
        raise ValueError("Not sent: the channel must match the commander's explicit request.")
    if channel == "commander":
        recipient = obj.get("recipient")
        if not isinstance(recipient, str) or not recipient.strip():
            raise ValueError("Not sent: commander channel requires an explicit recipient.")
        recipient = recipient.strip()
        if any(c in recipient for c in "\r\n/"):
            raise ValueError("Not sent: invalid recipient.")
        normalize = lambda value: re.sub(r"^(cmdr|commander)\s+", "", value.casefold().strip())
        if normalize(recipient) in (normalize(commander_name), "me", "myself", "self"):
            raise ValueError("Not sent: sending to yourself is not supported.")
        if not re.search(r'(?<!\w)' + re.escape(normalize(recipient)) + r'(?!\w)', normalize(intent)):
            raise ValueError("Not sent: recipient must be named in the commander's request.")


def latest_user_intent(events) -> str:
    for event in reversed(list(events)):
        if getattr(event, "kind", None) == "user":
            return str(event.content)
    return ""


def confirmed_send(events, baseline: set[int], message: str, channel: str, recipient: str = "") -> bool:
    destinations = {"local": {"local"}, "system": {"system"}, "wing": {"wing"},
                    "squadron": {"squadron"}, "commander": {recipient.casefold()}}
    for event in events:
        content = getattr(event, "content", {})
        if (id(event) not in baseline and getattr(event, "kind", None) == "game"
                and not getattr(event, "historic", True) and content.get("event") == "SendText"
                and content.get("Sent") is True and content.get("Message") == message
                and str(content.get("To", "")).casefold() in destinations[channel]):
            return True
    return False


def wait_for_send(read_events, baseline, message, channel, recipient="", timeout=3.0):
    deadline = monotonic() + timeout
    while True:
        if confirmed_send(read_events(), baseline, message, channel, recipient):
            return True
        if monotonic() >= deadline:
            return False
        sleep(0.05)


def spoken_activity(action_name: str) -> str:
    # Arguments and model-generated descriptions belong in Diagnostics only.
    return "Searching." if action_name == "web_search_agent" else "Checking."


def action_intent_allowed(name: str, intent: str) -> bool:
    if name == 'textMessage':
        return explicit_chat_intent(intent)
    if name in ('fireWeapons', 'fireWeaponsBuggy'):
        return bool(re.search(r'^(?:please\s+)?(fire|shoot|stop firing|stop shooting|cease fire|hold fire)\b', intent.casefold().strip()))
    if name in ('ejectAllCargo', 'ejectAllCargoBuggy'):
        return bool(re.search(r'^(?:please\s+)?(eject|dump|jettison|drop|purge)\b.*\b(cargo|materials)\b', intent.casefold()))
    return True
