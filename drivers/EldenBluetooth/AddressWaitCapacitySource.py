"""Give the explicit 59-rule address-wait profile a bounded 64-entry parser table."""
import hashlib
ORIGINAL='5cb9daa1c883ebd2b3d9c9e1a4d522cf528d0851250053e00ea4634a2974856a'

def source(original):
    if hashlib.sha256(original).hexdigest()!=ORIGINAL:raise ValueError('Original page parser differs')
    before=b'#define CS_TEXT_FIXUP_MAX 32'
    if original.count(before)!=1:raise ValueError('Ambiguous parser limit')
    return original.replace(before,b'#define CS_TEXT_FIXUP_MAX 64')
