from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class DummyProxy(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        print("Received payload:", post_data.decode('utf-8'))
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1677652288,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello from dummy proxy!"
                },
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21}
        }).encode())

if __name__ == '__main__':
    server_address = ('', 8085)
    httpd = HTTPServer(server_address, DummyProxy)
    print("Running dummy proxy on 8085...")
    httpd.serve_forever()
