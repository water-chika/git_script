from urllib.parse import urlparse

def remove_git_suffix(s):
    if s.endswith('.git'):
        s = s[0:len(s)-4]
    return s

def git_url_parse(url):
    parsed_url = urlparse(url)
    if parsed_url.scheme == '':
        loc = url.find(':')
        parsed_url = urlparse('ssh://' + url[0:loc] + '/' + url[loc+1:])
        print(parsed_url)
    return parsed_url

def is_same_repo(url0, url1):
    parsed_url0 = git_url_parse(url0)
    parsed_url1 = git_url_parse(url1)
    print(remove_git_suffix(parsed_url0.path), remove_git_suffix(parsed_url1.path))
    if remove_git_suffix(parsed_url0.path) == remove_git_suffix(parsed_url1.path):
        return True
