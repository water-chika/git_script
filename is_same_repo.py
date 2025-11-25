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
    if parsed_url.scheme == 'ssh' and parsed_url.netloc.count('@') > 0:
        loc = parsed_url.netloc.find('@')
        parsed_url = urlparse(parsed_url.scheme + '://' + parsed_url.netloc[loc+1:] + parsed_url.path)
    return parsed_url

def is_same_repo(url0, url1):
    parsed_url0 = git_url_parse(url0)
    parsed_url1 = git_url_parse(url1)
    print(parsed_url0, parsed_url1)
    if parsed_url0.netloc == parsed_url1.netloc and remove_git_suffix(parsed_url0.path) == remove_git_suffix(parsed_url1.path):
        return True
