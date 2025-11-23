from urllib.parse import urlparse

def remove_git_suffix(s):
    if s.endswith('.git'):
        s = s[0:len(s)-4]
    return s

def is_same_repo(url0, url1):
    parsed_url0 = urlparse(url0)
    parsed_url1 = urlparse(url1)
    print(remove_git_suffix(parsed_url0.path), remove_git_suffix(parsed_url1.path))
    if remove_git_suffix(parsed_url0.path) == remove_git_suffix(parsed_url1.path):
        return True
