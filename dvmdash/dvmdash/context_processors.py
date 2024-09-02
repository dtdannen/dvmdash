from .git_commit import GIT_COMMIT

def git_commit(request):
    return {'git_commit': GIT_COMMIT}