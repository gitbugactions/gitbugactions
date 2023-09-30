import os
from typing import Dict, Callable
from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileSystemEvent,
    FileSystemMovedEvent,
)


class LimitFolderSize(FileSystemEventHandler):
    """Allows to call an handler when a folder exceeds a certain size limit."""

    def __init__(self, folder_path: str, max_size: int, handler: Callable[[], None]):
        """
        Args:
            folder_path (str): The path of the folder.
            max_size (int): Max size in bytes the folder is allowed to have.
            handler (Callable[[], None]): Handler that is called.
        """
        super().__init__()
        self.total_size: int = 0
        self.file_size: Dict[str, int] = {}
        self.max_size: int = max_size
        self.handler = handler
        self.folder_path = folder_path
        self.observer = Observer()
        self.observer.schedule(self, folder_path, recursive=True)
        self.file_size[folder_path] = 4096
        for root, dirs, files in os.walk(folder_path):
            for name in files:
                path = os.path.join(root, name)
                size = os.path.getsize(path)
                self.file_size[path] = size
                self.total_size += size
            for dir in dirs:
                path = os.path.join(root, dir)
                size = os.path.getsize(path)
                self.file_size[path] = size
                self.total_size += size

    def __call_handler(self):
        self.handler()
        self.observer.stop()

    def start(self):
        self.observer.start()

    def stop(self):
        self.observer.stop()

    def on_created(self, event: FileSystemEvent):
        try:
            size = os.path.getsize(event.src_path)
        except FileNotFoundError:
            return
        self.total_size += size
        self.file_size[event.src_path] = size
        if self.total_size > self.max_size:
            self.__call_handler()

    def on_modified(self, event: FileSystemEvent):
        try:
            size = os.path.getsize(event.src_path)
        except FileNotFoundError:
            return
        if event.src_path in self.file_size:
            self.total_size += size - self.file_size[event.src_path]
        else:
            self.total_size += size
        self.file_size[event.src_path] = size
        if self.total_size > self.max_size:
            self.__call_handler()

    def on_deleted(self, event: FileSystemEvent):
        if event.src_path not in self.file_size:
            return
        self.total_size -= self.file_size[event.src_path]

    def on_moved(self, event: FileSystemMovedEvent):
        # The on_moved only includes files moved within the directory
        if event.src_path not in self.file_size:
            try:
                size = os.path.getsize(event.dest_path)
            except FileNotFoundError:
                return
            self.total_size += size
            self.file_size[event.dest_path] = size
        else:
            size = self.file_size[event.src_path]
            del self.file_size[event.src_path]
            self.file_size[event.dest_path] = size
