"""Test helper (no runtime use): page HTML without the viewer's OWN name in the top bar (decision 34). Tests that forbid a name
on a page check this text, so another user's name anywhere, or the viewer's name anywhere else on the page, still fails."""
import re

OWN_NAME = re.compile(r'<span class="eip-user-name">[^<]*</span>')


def without_own_name(response):
    return OWN_NAME.sub('', response.content.decode())
