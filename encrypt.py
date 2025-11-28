import os, json, struct
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_FILE = "secret.key"     # raw 32 byte PSK

# return 32 byte key
def load_key() -> bytes:

    # if no key create one 
    if not os.path.exists(KEY_FILE):
        key = os.urandom(32)
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        return key

    # else read in from file
    with open(KEY_FILE, "rb") as f:
        key = f.read()

    # catch bad keys
    if len(key) != 32:
        raise ValueError("secret.key must be exactly 32 bytes.")

    return key


def seal(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    aes = AESGCM(key)   # create aes cypher
    nonce = os.urandom(12)  # create 12 byte nonce 
    ciphertext = aes.encrypt(nonce, plaintext, aad)     # encrypt plaintext
    return nonce + ciphertext

def unseal(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    aes = AESGCM(key)   # create aes cypher
    nonce, ciphertext = blob[:12], blob[12:]    # seperate blob into nonce and ciphertext
    return aes.decrypt(nonce, ciphertext, aad)  # decrypt ciphertext
    

# read exactly n bytes 
def recvn(sock, n: int) -> Optional[bytes]:
    buf = bytearray()

    while len(buf) < n: # loop unitll buf has n bytes 
        chunk = sock.recv(n - len(buf))
    
        if not chunk:   # connection closed before n bytes recieved 
            return None
    
        buf.extend(chunk)   # append chunk to buffer
    
    return bytes(buf)

# send encrypted packedge with 
def send_sealed(sock, key: bytes, payload: bytes, aad: bytes = b"") -> None:
    blob = seal(key, payload, aad=aad)
    sock.sendall(struct.pack("!I", len(blob)))  # send header
    sock.sendall(blob)      # send payload

# recieve and decrypt
def recv_open(sock, key: bytes, aad: bytes = b"") -> Optional[bytes]:
    raw_len = recvn(sock, 4)    # read headder

    if not raw_len:
        return None

    (n,) = struct.unpack("!I", raw_len)     # get length of payload
    blob = recvn(sock, n)   # read payload

    # catch empty recv
    if not blob:
        return None

    return unseal(key, blob, aad=aad)   # decrypt and return


# json helpers for control

def send_json(sock, key: bytes, obj) -> None:
    data = json.dumps(obj).encode("utf-8")  # convert to json string 
    send_sealed(sock, key, data, aad=b"control")

def recv_json(sock, key: bytes):

    data = recv_open(sock, key, aad=b"control")

    # catch empty recv
    if data is None:
        return None

    return json.loads(data.decode("utf-8"))     # convert json to python object
