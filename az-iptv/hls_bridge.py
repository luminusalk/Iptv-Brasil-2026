# -*- coding: utf-8 -*-
"""Turn live HLS MPEG-TS feeds into local continuous MPEG-TS streams via background daemon."""

import os
import re
import socket
import threading
import time

try:
    import BaseHTTPServer as http_server
    import Queue as queue_module
    import SocketServer as socket_server
    import urllib2 as url_request
    from urllib import unquote, quote
    from urlparse import urljoin, urlsplit, parse_qs
except ImportError:
    import http.server as http_server
    import queue as queue_module
    import socketserver as socket_server
    import urllib.request as url_request
    from urllib.parse import unquote, quote, urljoin, urlsplit, parse_qs


MAX_PLAYLIST = 128 * 1024
MAX_SEGMENT = 4 * 1024 * 1024
BRIDGE_PORT = 8978
QUEUE_BUFFER_SIZE = 16
PREBUFFER_COUNT = 3


def parse_media_playlist(body, base_url):
    if not isinstance(body, str):
        body = body.decode('utf-8', 'replace')
    lines = [line.strip() for line in body.splitlines()]
    if not lines or lines[0] != '#EXTM3U':
        raise ValueError('Playlist HLS invalida')
    if any(line.startswith(('#EXT-X-KEY:', '#EXT-X-MAP:')) for line in lines):
        raise ValueError('HLS criptografado ou fMP4 nao suportado')
    marker = [line for line in lines if line.startswith('#EXT-X-MEDIA-SEQUENCE:')]
    if not marker:
        raise ValueError('Sequencia HLS ausente')
    first = int(marker[0].split(':', 1)[1])
    segments = []
    for line in lines:
        if not line or line.startswith('#'):
            continue
        address = urljoin(base_url, line)
        path = urlsplit(address).path.lower()
        if path.endswith('.ts') or '.ts' in path:
            segments.append((first + len(segments), address))
        else:
            raise ValueError('Segmento HLS nao e MPEG-TS: %s' % address)
    return segments


class HlsSequence(object):
    def __init__(self, media_url):
        self.media_url = media_url
        self.next_number = None

    def accept(self, body):
        segments = parse_media_playlist(body, self.media_url)
        fresh = [item for item in segments
                 if self.next_number is None or item[0] >= self.next_number]
        if fresh:
            self.next_number = fresh[-1][0] + 1
        return fresh


def _fetch(url, limit):
    response = url_request.urlopen(url, timeout=8)
    try:
        data = response.read(limit + 1)
    finally:
        response.close()
    if len(data) > limit:
        raise ValueError('Dados HLS grandes demais')
    return data


def _hls_producer(target_url, segment_queue, stop_event, report):
    sequence = HlsSequence(target_url)
    consecutive_errors = 0
    while not stop_event.is_set():
        try:
            body = _fetch(target_url, MAX_PLAYLIST)
            fresh = sequence.accept(body)
            if fresh:
                consecutive_errors = 0
                for _, segment_url in fresh:
                    if stop_event.is_set():
                        break
                    data = _fetch(segment_url, MAX_SEGMENT)
                    while not stop_event.is_set():
                        try:
                            segment_queue.put(data, timeout=1.0)
                            if report:
                                report('Queue put %d bytes (qsize=%d)' %
                                       (len(data), segment_queue.qsize()))
                            break
                        except queue_module.Full:
                            continue
                # Brief check interval to catch the next segment without delay
                stop_event.wait(0.2)
            else:
                # No new segment yet, recheck in 200ms
                stop_event.wait(0.2)
        except Exception as err:
            consecutive_errors += 1
            if report:
                report('HLS producer err: %s' % err)
            if consecutive_errors >= 8:
                if report:
                    report('HLS producer aborting after repeated failures')
                break
            stop_event.wait(0.8)
    try:
        segment_queue.put(None, timeout=1.0)
    except Exception:
        pass


class _ThreadingServer(socket_server.ThreadingMixIn, http_server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        socket_server.TCPServer.server_bind(self)
        self.server_name = 'localhost'
        self.server_port = self.socket.getsockname()[1]


class _Handler(http_server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_HEAD(self):
        self._headers()

    def _headers(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        if hasattr(self.server, 'report'):
            self.server.report('HTTP %s %s' % (self.command, self.path))
        if path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', '2')
            self.end_headers()
            return True
        if path != '/live.ts':
            self.send_error(404)
            return False
        self.send_response(200)
        self.send_header('Content-Type', 'video/MP2T')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Connection', 'close')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        return True

    def do_GET(self):
        if not self._headers():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == '/health':
            self.wfile.write(b'OK')
            return

        query_params = parse_qs(parsed.query)
        target_url = None
        if 'src' in query_params and query_params['src']:
            target_url = unquote(query_params['src'][0])
        if not target_url:
            target_url = getattr(self.server, 'media_url', None)

        if not target_url:
            self.send_error(400, 'Parametro src ausente')
            return

        channel_name = None
        if 'name' in query_params and query_params['name']:
            channel_name = unquote(query_params['name'][0])

        report = getattr(self.server, 'report', None)
        if report:
            msg = 'Cliente conectado para %s' % target_url
            if channel_name:
                msg = 'Cliente conectado canal [%s] para %s' % (channel_name, target_url)
            report(msg)

        if channel_name:
            try:
                from vfd_display import set_display
                set_display(channel_name, report)
            except Exception as vfd_err:
                if report:
                    report('Erro ao atualizar visor: %s' % vfd_err)

        segment_queue = queue_module.Queue(maxsize=QUEUE_BUFFER_SIZE)
        stop_event = threading.Event()

        producer_thread = threading.Thread(
            target=_hls_producer,
            args=(target_url, segment_queue, stop_event, report)
        )
        producer_thread.daemon = True
        producer_thread.start()

        # Pre-buffer: wait until we have at least PREBUFFER_COUNT segments or timeout
        start_wait = time.time()
        while segment_queue.qsize() < PREBUFFER_COUNT and (time.time() - start_wait) < 5.0:
            if stop_event.is_set():
                break
            time.sleep(0.1)

        if report:
            report('Prebuffer pronto: %d segmentos' % segment_queue.qsize())

        first_segment = True
        try:
            while not stop_event.is_set():
                try:
                    data = segment_queue.get(timeout=10.0)
                except queue_module.Empty:
                    if report:
                        report('Queue timeout: sem novos segmentos')
                    break

                if data is None:
                    break

                if first_segment:
                    idx = data.find(b'\x47')
                    if idx > 0:
                        data = data[idx:]
                    first_segment = False

                try:
                    self.wfile.write(data)
                    self.wfile.flush()
                except (IOError, socket.error) as err:
                    if report:
                        report('Cliente desconectou ao enviar: %s' % err)
                    break
        finally:
            stop_event.set()
            if report:
                report('Finalizando stream para cliente')


def is_bridge_healthy(port=BRIDGE_PORT):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.6)
    try:
        s.connect(('127.0.0.1', port))
        s.sendall(b"GET /health HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
        resp = s.recv(128)
        return b"200 OK" in resp or b"OK" in resp
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def ensure_bridge_daemon(report=None, port=BRIDGE_PORT):
    if is_bridge_healthy(port):
        if report:
            report('Bridge ativo na porta %d' % port)
        return 'http://127.0.0.1:%d' % port

    if report:
        report('Iniciando daemon do bridge na porta %d...' % port)

    server = _ThreadingServer(('0.0.0.0', port), _Handler)
    server.report = report if report else (lambda m: None)
    server.stop_event = threading.Event()

    pid = os.fork()
    if pid > 0:
        time.sleep(0.3)
        if report:
            report('Bridge daemon iniciado com PID %d' % pid)
        return 'http://127.0.0.1:%d' % port
    else:
        try:
            os.setsid()
        except Exception:
            pass

        try:
            null_fd = os.open(os.devnull, os.O_RDWR)
            for fd in (0, 1, 2):
                try:
                    os.dup2(null_fd, fd)
                except Exception:
                    pass
            if null_fd > 2:
                os.close(null_fd)
        except Exception:
            pass

        try:
            server.serve_forever()
        except Exception as e:
            try:
                with open('/mnt/plugin/plugin.video.az_iptv/bridge_daemon.err', 'a') as f:
                    f.write('%s\n' % e)
            except Exception:
                pass
        finally:
            os._exit(0)
