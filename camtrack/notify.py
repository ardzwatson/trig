"""Push notifications via ntfy (https://ntfy.sh) – free apps for Android/iOS, mirrors to Wear OS."""
import urllib.request


def send(cfg, title, message, jpeg=None):
    topic = cfg.get("ntfy_topic", "").strip()
    if not topic:
        return False, "no ntfy topic set"
    base = cfg.get("ntfy_server", "https://ntfy.sh").rstrip("/")
    headers = {"Title": title, "Priority": str(cfg.get("ntfy_priority", 4)), "Tags": "eyes"}
    if jpeg is not None:
        # attach snapshot: body is the image, message goes in a header
        headers.update({"Filename": "snapshot.jpg", "Message": message})
        body = jpeg
    else:
        body = message.encode()
    try:
        req = urllib.request.Request(f"{base}/{topic}", data=body, headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=10).read()
        return True, "sent"
    except Exception as e:  # network errors must never kill the tracker
        return False, str(e)
