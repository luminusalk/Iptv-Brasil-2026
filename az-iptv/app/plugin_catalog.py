# -*- coding: utf-8 -*-
"""Signed catalog and on-device cache. Uses only Python 2.7 standard libraries."""

import base64
import binascii
import hashlib
import json
import os
import re
import time


CATALOG_URL = ('https://raw.githubusercontent.com/luminusalk/'
               'Iptv-Brasil-2026/master/az-iptv/catalog.json')
MAX_BYTES = 512 * 1024
PUBLIC_EXPONENT = 65537
PUBLIC_MODULUS = int(
    'c2f5cf9c9c1e8c43e03005a0748418224082c807da95dd02c36b95a3e7297d02'
    'e028d6e4e9decb7650cc2d28a03d42c18a5987f299497ad083c3e89c628a78'
    'a3e0c660a7dabd54bb2107de408e964a17264abe5d92f5c254b62c0b4c198d'
    '683b0971ff1b7185f14dd52a8c3cf936015785a82c46b57eaa34833b0360c91'
    'bee38d9eaea06ecec842a53079761b374644fc3f13f355fb44e144ade96d3603'
    'b597dcbcb99f9605b6aaed5d7f6ec1879fe2d2d6947eef5b06d9ae81e6401c0'
    '97e7d7a9ff35fecd1d0c7172f4ced56428c532f0b0a42f307ad80b124d5b46c'
    'bb88d01580e123c58fff5f66d44b7ae998152061f56afb86096ba18137988d4d6'
    'eafa01', 16)
SHA256_DER = bytes(bytearray.fromhex('3031300d060960864801650304020105000420'))
VALID_ID = re.compile(r'^[a-z0-9_-]{1,40}$')
try:
    integer_types = (int, long)
    text_types = (str, unicode)
except NameError:
    integer_types = (int,)
    text_types = (str,)


class CatalogError(Exception):
    pass


def canonical_payload(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True).encode('ascii')


def _verify_signature(payload, signature):
    try:
        raw = base64.b64decode(signature)
        size = (PUBLIC_MODULUS.bit_length() + 7) // 8
        if len(raw) != size:
            return False
        number = pow(int(binascii.hexlify(raw), 16), PUBLIC_EXPONENT,
                     PUBLIC_MODULUS)
        encoded = binascii.unhexlify(('%0*x' % (size * 2, number)).encode('ascii'))
        digest = hashlib.sha256(canonical_payload(payload)).digest()
        expected = SHA256_DER + digest
        padding_size = size - len(expected) - 3
        return (padding_size >= 8 and
                encoded == b'\x00\x01' + b'\xff' * padding_size + b'\x00' + expected)
    except (TypeError, ValueError, OverflowError):
        return False


def _validate_payload(payload):
    if not isinstance(payload, dict) or payload.get('schema') != 1:
        raise CatalogError('Formato de catalogo invalido')
    revision = payload.get('revision')
    if isinstance(revision, bool) or not isinstance(revision, integer_types) or revision < 1:
        raise CatalogError('Revisao invalida')
    lists = payload.get('lists')
    if not isinstance(lists, list) or len(lists) > 30:
        raise CatalogError('Listas invalidas')
    seen = set()
    count = 0
    for channel_list in lists:
        if not isinstance(channel_list, dict):
            raise CatalogError('Lista invalida')
        list_id = channel_list.get('id')
        title = channel_list.get('title')
        channels = channel_list.get('channels')
        if (not isinstance(list_id, text_types) or not VALID_ID.match(list_id) or
                list_id in seen or not isinstance(title, text_types) or
                not 1 <= len(title) <= 100 or not isinstance(channels, list)):
            raise CatalogError('Metadados da lista invalidos')
        seen.add(list_id)
        for channel in channels:
            count += 1
            if count > 2000 or not isinstance(channel, dict):
                raise CatalogError('Canais invalidos')
            name = channel.get('name')
            url = channel.get('url')
            if (not isinstance(name, text_types) or not 1 <= len(name) <= 120 or
                    not isinstance(url, text_types) or not 1 <= len(url) <= 2048 or
                    not url.startswith(('https://', 'http://'))):
                raise CatalogError('Canal invalido')
    app = payload.get('app')
    if app is not None:
        if not isinstance(app, dict):
            raise CatalogError('Atualizacao do aplicativo invalida')
        version = app.get('version')
        url = app.get('url')
        digest = app.get('sha256')
        if (not isinstance(version, text_types) or
                not re.match(r'^\d+\.\d+\.\d+$', version) or
                not isinstance(url, text_types) or
                not url.startswith('https://') or len(url) > 2048 or
                not isinstance(digest, text_types) or
                not re.match(r'^[0-9a-f]{64}$', digest)):
            raise CatalogError('Atualizacao do aplicativo invalida')
    return payload


def validate_manifest(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise CatalogError('Catalogo grande demais')
    try:
        manifest = json.loads(raw.decode('utf-8'))
        payload = manifest['payload']
        signature = manifest['signature']
    except (ValueError, UnicodeError, KeyError, TypeError):
        raise CatalogError('Catalogo malformado')
    if not _verify_signature(payload, signature):
        raise CatalogError('Assinatura do catalogo invalida')
    return _validate_payload(payload)


class CatalogStore(object):
    def __init__(self, directory):
        self.directory = directory
        self.path = os.path.join(directory, 'catalog.json')
        self.checked_path = os.path.join(directory, 'checked_at.txt')

    def load(self):
        try:
            with open(self.path, 'rb') as handle:
                return validate_manifest(handle.read(MAX_BYTES + 1))
        except (IOError, CatalogError):
            return None

    def due(self, interval=3600):
        try:
            with open(self.checked_path, 'r') as handle:
                checked = float(handle.read())
            elapsed = time.time() - checked
            return elapsed < 0 or elapsed >= interval
        except (IOError, ValueError):
            return True

    def mark_checked(self):
        if not os.path.isdir(self.directory):
            os.makedirs(self.directory)
        with open(self.checked_path, 'w') as handle:
            handle.write(str(time.time()))

    def update(self, fetcher):
        try:
            raw = fetcher()
            new_payload = validate_manifest(raw)
            old_payload = self.load()
            if old_payload and new_payload['revision'] < old_payload['revision']:
                raise CatalogError('Revisao anterior ao catalogo instalado')
            if not os.path.isdir(self.directory):
                os.makedirs(self.directory)
            temporary = self.path + '.tmp'
            try:
                with open(temporary, 'wb') as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                replace = getattr(os, 'replace', os.rename)
                replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return new_payload
        finally:
            self.mark_checked()


def fetch_catalog():
    try:
        import urllib2 as urlrequest
    except ImportError:
        import urllib.request as urlrequest
    response = urlrequest.urlopen(CATALOG_URL, timeout=6)
    try:
        return response.read(MAX_BYTES + 1)
    finally:
        response.close()
