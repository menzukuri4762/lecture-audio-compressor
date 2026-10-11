import os
import sys
import socket
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class CustomHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        directory = os.path.dirname(os.path.abspath(__file__))
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format, *args):
        # Clean logging
        pass

def run_server(port=8080):
    local_ip = get_local_ip()
    server_address = ("", port)

    # Find open port
    while True:
        try:
            httpd = HTTPServer(server_address, CustomHandler)
            break
        except OSError:
            port += 1
            server_address = ("", port)

    mobile_url = f"http://{local_ip}:{port}/"
    pc_url = f"http://localhost:{port}/"

    print("========================================================")
    print("   Lecture Audio AI Compressor - Mobile Web Server")
    print("========================================================")
    print(f"\n[Smartphone URL]:")
    print(f"  --> {mobile_url}\n")
    print("How to connect:")
    print("  1. Connect your smartphone to the SAME Wi-Fi as this PC.")
    print(f"  2. Open Safari or Chrome on your phone, and visit:\n     {mobile_url}")
    print("  3. (Recommended) Add to Home Screen for 1-tap launch!\n")
    print("Press Ctrl+C to stop the server.")
    print("========================================================\n")

    # Automatically open in PC browser
    webbrowser.open(pc_url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    run_server()
