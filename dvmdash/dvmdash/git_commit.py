import subprocess

def get_git_commit():
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
    except:
        return 'unknown'

GIT_COMMIT = get_git_commit()