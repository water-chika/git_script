from urllib.parse import urlparse

def is_same_repo(url0, url1):
    parsed_url0 = urlparse(url0)
    parsed_url1 = urlparse(url1)
    print(remove_git_suffix(parsed_url0.path), remove_git_suffix(parsed_url1.path))
    if remove_git_suffix(parsed_url0.path) == remove_git_suffix(parsed_url1.path):
        return True
