import os
import shutil
import time
import pygit2

def delete_repo_clone(repo_clone: pygit2.Repository):
    def retry_remove(function, path, excinfo):
        time.sleep(0.5)
        if os.path.exists(path) and os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path) and os.path.isfile(path):
            os.remove(path)

    repo_clone.free()
    if os.path.exists(repo_clone.workdir):
        shutil.rmtree(repo_clone.workdir, onerror=retry_remove)