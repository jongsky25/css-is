"""Travel tests obtain the same actor-bound form key as a real browser."""
import re


def operation_id(client):
    page = client.get('/travel/new')
    match = re.search(r'name="operation_id" value="([a-f0-9-]+)"', page.text)
    return match[1] if match else ''  # Feature-disabled pages have no form.
