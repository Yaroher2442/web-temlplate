import hashlib
import logging
import random
import string
import sys
from base64 import b64encode, b64decode
from typing import Iterable
from uuid import uuid4

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


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


class AESCrypto(BaseCrypto):
    class DataStruct:
        __slots__ = ["cipher_text", "salt", "nonce", "tag"]

        def __init__(self, cipher_text, salt, nonce, tag):
            self.cipher_text = cipher_text
            self.salt = salt
            self.nonce = nonce
            self.tag = tag

        def decode(self):
            for var, val in self.__dict__().items():
                setattr(self, var, b64decode(val))

        def encode(self):
            encoding = sys.getdefaultencoding()
            for var, val in self.__dict__().items():
                setattr(self, var, b64encode(val).decode(encoding))

        def __dict__(self):
            return {"cipher_text": self.cipher_text,
                    "salt": self.salt,
                    "nonce": self.nonce,
                    "tag": self.tag}

        def __str__(self):
            return "\n".join([f"{k} : {v}" for k, v in self.__dict__().items()])

    _data_password: str
    _n_factor: int
    _block_size: int
    _threads_num: int
    _key_len: int

    def __init__(self, secret: str):
        super(AESCrypto, self).__init__()
        self._data_password = secret
        self._n_factor = 2 ** 14
        self._block_size = 8
        self._threads_num = 1
        self._key_len = 32

    def encrypt(self, plain_text: str) -> DataStruct:
        salt = get_random_bytes(AES.block_size)
        private_key = hashlib.scrypt(
            self._data_password.encode(), salt=salt, n=self._n_factor, r=self._block_size, p=self._threads_num,
            dklen=self._key_len)
        cipher_config = AES.new(private_key, AES.MODE_GCM)
        cipher_text, tag = cipher_config.encrypt_and_digest(bytes(plain_text, sys.getdefaultencoding()))
        return AESCrypto.DataStruct(cipher_text, salt, cipher_config.nonce, tag)

    def decrypt(self, aes_struct: DataStruct) -> str:
        aes_struct.decode()
        private_key = hashlib.scrypt(
            self._data_password.encode(), salt=aes_struct.salt, n=self._n_factor, r=self._block_size,
            p=self._threads_num,
            dklen=self._key_len)
        cipher = AES.new(private_key, AES.MODE_GCM, nonce=aes_struct.nonce)
        decrypted = cipher.decrypt_and_verify(aes_struct.cipher_text, aes_struct.tag)
        return decrypted

    @property
    def key_len(self):
        return self._key_len


class RsaCrypto(BaseCrypto):
    pass
