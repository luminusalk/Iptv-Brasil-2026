# -*- coding: utf-8 -*-
"""Video menu for the Azamerica's built-in XBMC-compatible environment."""

import os
import sys

import xbmcgui
import xbmcplugin

from playlist import read_page
from plugin_catalog import CatalogStore, fetch_catalog
from app_update import fetch_app, install_update, installed_version, newer_version


ROOT = os.path.dirname(os.path.abspath(__file__))
LIST_DIR = os.path.join(ROOT, 'lists')
PAGE_SIZE = 200
CATALOG = CatalogStore(os.path.join(ROOT, 'catalog_cache'))


def fields():
    result = {}
    query = sys.argv[2].lstrip('?') if len(sys.argv) > 2 else ''
    for part in query.split('&'):
        if '=' in part:
            key, value = part.split('=', 1)
            result[key] = value
    return result


def playlists():
    return sorted(name for name in os.listdir(LIST_DIR)
                  if name.lower().endswith(('.m3u', '.m3u8')))


def add_folder(handle, label, address):
    xbmcplugin.addDirectoryItem(handle, address, xbmcgui.ListItem(label), True)


def add_video(handle, label, address):
    item = xbmcgui.ListItem(label)
    item.setProperty('IsPlayable', 'true')
    xbmcplugin.addDirectoryItem(handle, address, item, False)


def show_root(handle, base):
    if CATALOG.due():
        try:
            CATALOG.update(fetch_catalog)
        except Exception:
            pass
    catalog = CATALOG.load()
    if catalog:
        add_folder(handle, 'Canais do GitHub (revisao %d)' % catalog['revision'],
                   base + '?mode=cloud')
        app = catalog.get('app')
        if app and newer_version(app['version'], installed_version(ROOT)):
            add_folder(handle, 'Atualizar aplicativo para ' + app['version'],
                       base + '?mode=update_app')
    add_folder(handle, 'Atualizar catalogo do GitHub', base + '?mode=update')
    if playlists():
        add_folder(handle, 'Minhas listas M3U', base + '?mode=local')
    add_video(handle, 'Teste offline (15 segundos)', os.path.join(ROOT, 'demo.mp4'))
    sample = os.path.join(ROOT, 'sample720.mp4')
    if os.path.exists(sample):
        add_video(handle, 'Teste TV Cultura 720p (15 segundos)', sample)
    xbmcplugin.endOfDirectory(handle)


def show_local_lists(handle, base):
    for index, name in enumerate(playlists()):
        label = os.path.splitext(name)[0]
        add_folder(handle, label, base + '?list=%d&page=0' % index)
    xbmcplugin.endOfDirectory(handle)


def show_cloud_lists(handle, base):
    catalog = CATALOG.load()
    if catalog:
        for channel_list in catalog['lists']:
            add_folder(handle, channel_list['title'],
                       base + '?mode=cloud_list&id=' + channel_list['id'] + '&page=0')
    xbmcplugin.endOfDirectory(handle)


def show_cloud_channels(handle, base, args):
    catalog = CATALOG.load()
    if not catalog:
        show_root(handle, base)
        return
    try:
        page = int(args.get('page', '0'))
        if page < 0:
            raise ValueError('Invalid page')
    except ValueError:
        show_root(handle, base)
        return
    for channel_list in catalog['lists']:
        if channel_list['id'] == args.get('id'):
            channels = channel_list['channels']
            if page:
                add_folder(handle, 'Pagina anterior',
                           base + '?mode=cloud_list&id=%s&page=%d' %
                           (channel_list['id'], page - 1))
            for channel in channels[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
                add_video(handle, channel['name'], channel['url'])
            if (page + 1) * PAGE_SIZE < len(channels):
                add_folder(handle, 'Proxima pagina',
                           base + '?mode=cloud_list&id=%s&page=%d' %
                           (channel_list['id'], page + 1))
            xbmcplugin.endOfDirectory(handle)
            return
    show_root(handle, base)


def update_catalog(handle, base):
    try:
        catalog = CATALOG.update(fetch_catalog)
        xbmcgui.Dialog().ok('Az IPTV',
                            'Catalogo atualizado. Revisao %d.' % catalog['revision'])
    except Exception as error:
        xbmcgui.Dialog().ok('Az IPTV', 'Falha ao atualizar: %s' % error)
    show_root(handle, base)


def update_app(handle, base):
    catalog = CATALOG.load()
    if not catalog or not catalog.get('app'):
        xbmcgui.Dialog().ok('Az IPTV', 'Nenhuma atualizacao disponivel.')
    else:
        try:
            install_update(ROOT, catalog['app'], fetch_app)
            xbmcgui.Dialog().ok('Az IPTV',
                                'Aplicativo atualizado. Saia e abra o XBMC novamente.')
        except Exception as error:
            xbmcgui.Dialog().ok('Az IPTV', 'Falha na atualizacao: %s' % error)
    show_root(handle, base)


def show_playlist(handle, base, args):
    try:
        index = int(args['list'])
        page = int(args.get('page', '0'))
        names = playlists()
        if index < 0 or index >= len(names) or page < 0:
            raise ValueError('Invalid list or page')
    except (KeyError, ValueError):
        show_root(handle, base)
        return

    path = os.path.join(LIST_DIR, names[index])
    channels, more = read_page(path, page, PAGE_SIZE)
    if page:
        add_folder(handle, 'Pagina anterior',
                   base + '?list=%d&page=%d' % (index, page - 1))
    for label, address in channels:
        add_video(handle, label, address)
    if more:
        add_folder(handle, 'Proxima pagina',
                   base + '?list=%d&page=%d' % (index, page + 1))
    xbmcplugin.endOfDirectory(handle)


def main():
    handle = int(sys.argv[1])
    base = sys.argv[0]
    args = fields()
    if args.get('mode') == 'update':
        update_catalog(handle, base)
    elif args.get('mode') == 'update_app':
        update_app(handle, base)
    elif args.get('mode') == 'cloud':
        show_cloud_lists(handle, base)
    elif args.get('mode') == 'cloud_list':
        show_cloud_channels(handle, base, args)
    elif args.get('mode') == 'local':
        show_local_lists(handle, base)
    elif 'list' in args:
        show_playlist(handle, base, args)
    else:
        show_root(handle, base)


if __name__ == '__main__':
    main()
