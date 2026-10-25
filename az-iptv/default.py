# -*- coding: utf-8 -*-
"""Video menu for the Azamerica's built-in XBMC-compatible environment."""

import os
import sys
import time
import traceback

try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote

import xbmcgui
import xbmcplugin

from playlist import read_page
from plugin_catalog import CatalogStore, fetch_catalog
from hls_bridge import ensure_bridge_daemon
try:
    from vfd_display import set_display
except ImportError:
    def set_display(text, logger=None):
        return False


ROOT = os.path.dirname(os.path.abspath(__file__))
LIST_DIR = os.path.join(ROOT, 'lists')
PAGE_SIZE = 200
CATALOG = CatalogStore(os.path.join(ROOT, 'catalog_cache'))
LIVE_CULTURA_540 = ('https://player-tvcultura.stream.uol.com.br/live/'
                    'tvcultura_lsd.m3u8?vhost=player-tvcultura.stream.uol.com.br')


def record(message):
    try:
        with open(os.path.join(ROOT, 'live_debug.txt'), 'a') as output:
            output.write('%s %s\n' % (int(time.time()), message))
    except Exception:
        pass


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


def add_folder(handle, label, address, logo=None):
    item = xbmcgui.ListItem(label)
    if logo:
        item.setThumbnailImage(logo)
        item.setIconImage(logo)
    xbmcplugin.addDirectoryItem(handle, address, item, True)


def add_video(handle, label, address, logo=None):
    item = xbmcgui.ListItem(label)
    item.setProperty('IsPlayable', 'true')
    if logo:
        item.setThumbnailImage(logo)
        item.setIconImage(logo)
    xbmcplugin.addDirectoryItem(handle, address, item, False)


def local_ip():
    import socket
    route = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        route.connect(('192.168.137.1', 9))
        return route.getsockname()[0]
    finally:
        route.close()


def make_video_url(url, name=None):
    if not url:
        return url
    if '.m3u8' in url.lower():
        try:
            ensure_bridge_daemon(record)
            bridge_url = 'http://127.0.0.1:8978/live.ts?src=' + quote(url)
            if name:
                bridge_url += '&name=' + quote(name)
            return bridge_url
        except Exception:
            record(traceback.format_exc())
    return url


def show_root(handle, base):
    if CATALOG.due():
        try:
            CATALOG.update(fetch_catalog)
        except Exception:
            pass
    catalog = CATALOG.load()
    if catalog:
        add_folder(handle, 'Canais ao Vivo', base + '?mode=cloud')

    # TV Cultura ao vivo via HLS Bridge local em background
    try:
        ensure_bridge_daemon(record)
        cultura_bridge_url = make_video_url(LIVE_CULTURA_540, 'TV Cultura')
        add_video(handle, 'TV Cultura ao vivo [720p HD]', cultura_bridge_url,
                  'http://beststorage4you.com:80/logoscanais/TVCULTURA.png')
    except Exception:
        record(traceback.format_exc())

    if playlists():
        add_folder(handle, 'Minhas Listas M3U', base + '?mode=local')

    add_folder(handle, 'Atualizar Lista de Canais', base + '?mode=update')
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
                logo = channel.get('logo')
                add_video(handle, channel['name'], make_video_url(channel['url'], channel['name']), logo)
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
        add_video(handle, label, make_video_url(address, label))
    if more:
        add_folder(handle, 'Proxima pagina',
                   base + '?list=%d&page=%d' % (index, page + 1))
    xbmcplugin.endOfDirectory(handle)


def main():
    handle = int(sys.argv[1])
    base = sys.argv[0]
    args = fields()
    try:
        set_display('AZ IPTV', record)
    except Exception:
        pass
    if args.get('mode') == 'update':
        update_catalog(handle, base)
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
