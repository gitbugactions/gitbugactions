import docker
import threading


class DockerClient:
    __instance: docker.DockerClient = None
    __get_instance_lock: threading.Lock = threading.Lock()

    @staticmethod
    def getInstance():
        with DockerClient.__get_instance_lock:
            if DockerClient.__instance == None:
                DockerClient()
            return DockerClient.__instance

    def __init__(self):
        if DockerClient.__instance != None:
            raise Exception("This class is a singleton!")
        else:
            DockerClient.__instance = docker.from_env(timeout=1200)
