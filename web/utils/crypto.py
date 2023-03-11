import hashlib
import random
import string
import sys
from typing import Iterable


# from Crypto.Cipher import AES
# from Crypto.Random import get_random_bytes


class BaseCrypto:
    class DataStruct:
        pass

    def __init__(self):
        pass

    @staticmethod
    def encrypt_password(passw: str, salt_len: int = 10) -> Iterable[str]:
        salt = ''.join(random.choices(string.ascii_uppercase + string.digits, k=salt_len))
        crypted_pass = hashlib.sha256((passw + salt).encode(sys.getdefaultencoding())).hexdigest()
        return crypted_pass, salt

    @staticmethod
    def verify_password(raw_pass: str, db_pass: str, salt: str):
        crypted_pass = hashlib.sha256((raw_pass + salt).encode(sys.getdefaultencoding())).hexdigest()
        return db_pass == crypted_pass

    def encrypt(self, plain_text: str) -> DataStruct:
        raise NotImplementedError()

    def decrypt(self, aes_struct: DataStruct) -> str:
        raise NotImplementedError()
