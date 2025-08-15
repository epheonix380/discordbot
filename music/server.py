import http.server
import socketserver
import threading
import urllib.parse


import http.server
import socketserver
import threading
import urllib.parse

# This is a place to store the OAuth code received from the callback.
# The main bot script will check this variable.
auth_code_global = None

class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """
    A custom handler to process the incoming HTTP request from the Spotify OAuth callback.
    """
    def do_GET(self):
        """
        Handles GET requests, which is what the Spotify redirect will be.
        """
        global auth_code_global

        # Parse the URL to get the query parameters
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)

        # We're only interested in the `code` parameter
        if 'code' in query_params:
            auth_code_global = query_params['code'][0]
            print(f"Received OAuth code: {auth_code_global}")

            # Send a successful response to the user's browser
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authentication successful!</h1><p>You can close this window.</p></body></html>")
            
            # This is a crucial step to stop the server after the callback is received
            # We shut down the server in a separate thread to prevent a deadlock
            threading.Thread(target=self.server.shutdown).start()
        else:
            # Handle cases where the request is not an OAuth callback
            self.send_error(404, "Page Not Found")


def run_temporary_server(port=8080):
    """
    Starts and runs a temporary web server on a given port.
    """
    with socketserver.TCPServer(("", port), OAuthCallbackHandler) as httpd:
        print(f"Starting temporary OAuth server on port {port}...")
        httpd.serve_forever()
        print("Server shut down.")

def run_web_server(callback):
    # Example of how you would use this in your main script
    server_thread = threading.Thread(target=run_temporary_server)
    server_thread.start()

    # In your bot, you would send the user the Spotify auth URL here, e.g.:
    # "https://accounts.spotify.com/authorize?response_type=code&client_id=...&scope=...&redirect_uri=http://localhost:8080"
    
    # Wait for the server thread to finish, indicating the code has been received
    server_thread.join()
    
    # Now you can use the `auth_code_global` to get the access token
    if auth_code_global:
        callback(auth_code_global)
    else:
        return None