# -*- coding: utf-8 -*-
"""Install a catalog-authorized code update without touching user playlists."""

import hashlib
import io
import os
import re
import zipfile


CODE_FILES = ('addon.xml', 'plugin_catalog.py', 'playlist.py',
              'app_update.py', 'default.py')
MAX_ZIP_BYTES = 512 * 1024
try:
    text_types = (str, unicode)
except NameError:
    text_types = (str,)


class AppUpdateError(Exception):
    pass


def version_tuple(value):
    if not re.match(r'^\d+(\.\d+){1,3}$', value):
        raise AppUpdateError('Versao invalida')
    return tuple(int(part) for part in value.split('.'))


def newer_version(candidate, installed):
    return version_tuple(candidate) > version_tuple(installed)


def _version_from_xml(raw):
    match = re.search(br'<addon\b[^>]*\bversion="([0-9.]+)"', raw)
    if not match:
        raise AppUpdateError('addon.xml sem versao')
    return match.group(1).decode('ascii')


def installed_version(root):
    with open(os.path.join(root, 'addon.xml'), 'rb') as handle:
        return _version_from_xml(handle.read(8192))


def _read_bundle(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_ZIP_BYTES:
        raise AppUpdateError('Pacote grande demais')
    try:
        bundle = zipfile.ZipFile(io.BytesIO(raw), 'r')
        infos = bundle.infolist()
        if (len(infos) != len(CODE_FILES) or
                set(info.filename for info in infos) != set(CODE_FILES) or
                sum(info.file_size for info in infos) > MAX_ZIP_BYTES):
            raise AppUpdateError('Arquivos inesperados no pacote')
        return dict((info.filename, bundle.read(info)) for info in infos)
    except (zipfile.BadZipfile, IOError, RuntimeError):
        raise AppUpdateError('Pacote ZIP invalido')


def install_update(root, app_spec, fetcher):
    version = app_spec.get('version')
    url = app_spec.get('url', '')
    digest = app_spec.get('sha256', '')
    if (not isinstance(version, text_types) or not isinstance(url, text_types) or
            not url.startswith('https://') or
            not re.match(r'^[0-9a-f]{64}$', digest) or
            not newer_version(version, installed_version(root))):
        raise AppUpdateError('Atualizacao invalida ou antiga')
    raw = fetcher(url)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise AppUpdateError('Hash do aplicativo nao confere')
    files = _read_bundle(raw)
    if _version_from_xml(files['addon.xml']) != version:
        raise AppUpdateError('Versao do pacote nao confere')

    replace = getattr(os, 'replace', os.rename)
    backup = {}
    installed = []
    try:
        for name in CODE_FILES:
            path = os.path.join(root, name)
            with open(path, 'rb') as handle:
                backup[name] = handle.read()
            temporary = path + '.new'
            with open(temporary, 'wb') as handle:
                handle.write(files[name])
                handle.flush()
                os.fsync(handle.fileno())
        for name in CODE_FILES:
            path = os.path.join(root, name)
            replace(path + '.new', path)
            installed.append(name)
    except Exception:
        for name in installed:
            path = os.path.join(root, name)
            with open(path + '.restore', 'wb') as handle:
                handle.write(backup[name])
            replace(path + '.restore', path)
        raise
    finally:
        for name in CODE_FILES:
            temporary = os.path.join(root, name + '.new')
            if os.path.exists(temporary):
                os.unlink(temporary)


def fetch_app(url):
    try:
        import urllib2 as urlrequest
    except ImportError:
        import urllib.request as urlrequest
    response = urlrequest.urlopen(url, timeout=15)
    try:
        return response.read(MAX_ZIP_BYTES + 1)
    finally:
        response.close()
