"""One-off interactive login that handles EZVIZ's MFA code and caches the token."""
import json, os, getpass
from pyezviz import EzvizClient
from pyezviz.exceptions import EzvizAuthVerificationCode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.environ.get("EZVIZ_TOKEN_PATH", os.path.join(ROOT, "ezviz_token.json"))
acct = os.environ.get("EZVIZ_ACCOUNT") or input("EZVIZ account: ")
pw = os.environ.get("EZVIZ_PASSWORD") or getpass.getpass("Password: ")
c = EzvizClient(acct, pw, os.environ.get("EZVIZ_URL", "apiieu.ezvizlife.com"))
try:
    tok = c.login()
except EzvizAuthVerificationCode:
    tok = c.login(sms_code=int(input("MFA code sent to you: ")))
json.dump(tok, open(path, "w"))
print("saved", path)
