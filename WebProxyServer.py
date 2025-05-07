import os
import sys
import socket
from urllib.parse import urlparse

def main():
    if len(sys.argv) < 2:
        print('Usage: python3 ProxyServer.py [listen_ip]')
        sys.exit(1)

    listen_ip   = sys.argv[1]
    listen_port = 8888
    cache_dir   = './cache'
    os.makedirs(cache_dir, exist_ok=True)

    # 1) Create & bind the listening socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((listen_ip, listen_port))
    server.listen(5)
    print(f"[*] Proxy listening on {listen_ip}:{listen_port}")

    while True:
        client_sock, client_addr = server.accept()
        print('[*] Connection from', client_addr)

        # 2) Read full HTTP request headers
        request_data = b''
        while True:
            chunk = client_sock.recv(4096)
            if not chunk:
                break
            request_data += chunk
            if b'\r\n\r\n' in request_data:
                break

        if not request_data:
            client_sock.close()
            continue

        try:
            request_text = request_data.decode()
        except UnicodeDecodeError:
            client_sock.close()
            continue

        # 3) Parse the request line
        lines        = request_text.split('\r\n')
        request_line = lines[0]
        parts = request_line.split()
        if len(parts) < 3:
            client_sock.close()
            continue
        method, raw_url, version = parts

        # 4) Determine target_host & path
        parsed = urlparse(raw_url)
        if parsed.scheme and parsed.netloc:
            # Browser proxy mode: GET http://host/path HTTP/1.x
            target_host = parsed.netloc
            path        = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
        else:
            # URL-hack mode: GET /host/path HTTP/1.x
            segs = raw_url.lstrip('/').split('/', 1)
            target_host = segs[0]
            path        = '/' + segs[1] if len(segs) > 1 else '/'

        print(f"[*] Fetching → {target_host}{path}")

        # 5) Build a safe cache filename
        clean_path = path.lstrip('/')
        if clean_path == '':
            cache_name = target_host
        else:
            cache_name = target_host + '_' + clean_path.replace('/', '_')
        cache_path = os.path.join(cache_dir, cache_name)

        # 6) Serve from cache if available
        if os.path.exists(cache_path):
            print('[*] Cache HIT:', cache_path)
            with open(cache_path, 'rb') as f:
                client_sock.sendall(f.read())
            client_sock.close()
            continue

        # 7) Cache miss → fetch from the real server
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as remote:
                remote.connect((target_host, 80))
                # Force the server to close after sending
                req = (
                    f"GET {path} HTTP/1.0\r\n"
                    f"Host: {target_host}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ).encode()
                remote.sendall(req)

                # Read until EOF
                response = b''
                while True:
                    buf = remote.recv(4096)
                    if not buf:
                        break
                    response += buf

        except Exception as e:
            print('[!] Fetch error:', e)
            response = (
                "HTTP/1.0 502 Bad Gateway\r\n"
                "Content-Type: text/html\r\n\r\n"
                "<html><body><h1>502 Bad Gateway</h1></body></html>"
            ).encode()

        # 8) Cache the response
        try:
            with open(cache_path, 'wb') as f:
                f.write(response)
            print('[*] Cached →', cache_path)
        except Exception as e:
            print('[!] Cache write failed:', e)

        # 9) Relay the response back to the client
        client_sock.sendall(response)
        client_sock.close()

if __name__ == '__main__':
    main()