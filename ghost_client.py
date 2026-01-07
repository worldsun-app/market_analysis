import requests
import jwt
import datetime
import os
import json

class GhostClient:
    def __init__(self, url: str, admin_key: str):
        """
        Initialize Ghost Client.
        :param url: Ghost Blog URL (e.g., https://your-blog.ghost.io)
        :param admin_key: Ghost Admin API Key
        """
        self.url = url.rstrip('/')
        self.admin_key = admin_key
        self.session = requests.Session()

    def _get_headers(self):
        """Generate JWT token and return headers."""
        id_str, secret = self.admin_key.split(':')
        
        # Prepare header and payload
        iat = int(datetime.datetime.now().timestamp())
        header = {'alg': 'HS256', 'typ': 'JWT', 'kid': id_str}
        payload = {
            'iat': iat,
            'exp': iat + 300,  # 5 minutes
            'aud': '/admin/'
        }

        # Create the token (secret is hex text)
        token = jwt.encode(payload, bytes.fromhex(secret), algorithm='HS256', headers=header)

        return {
            'Authorization': f'Ghost {token}'
        }

    def create_post(self, title: str, html_content: str, status: str = 'published', tags: list = None, codeinjection_head: str = None, codeinjection_foot: str = None):
        """
        Create a post in Ghost.
        :param title: Post title
        :param html_content: The HTML body of the post
        :param status: 'published' or 'draft'
        :param tags: Optional list of tags (dict objects or strings if verified)
        :param codeinjection_head: Optional CSS/JS for the header
        :param codeinjection_foot: Optional CSS/JS for the footer
        """
        endpoint = f"{self.url}/ghost/api/admin/posts/?source=html"
        headers = self._get_headers()
        
        post_data = {
            "title": title,
            "html": html_content,
            "status": status,
        }
        
        if tags:
             post_data["tags"] = tags
        if codeinjection_head:
            post_data["codeinjection_head"] = codeinjection_head
        if codeinjection_foot:
            post_data["codeinjection_foot"] = codeinjection_foot

        body = {
            "posts": [post_data]
        }

        try:
            response = self.session.post(endpoint, json=body, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[!] Ghost API Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"    Response: {e.response.text}")
            return None
