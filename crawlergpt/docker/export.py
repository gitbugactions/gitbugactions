import os
import time
import hashlib
import shutil
import uuid
import tempfile
import json
import pickle
import docker
import tarfile
from dataclasses import dataclass
from typing import Dict

from docker.models.containers import Container
from docker.models.images import Image

@dataclass
class Layer:
    name: str
    path: str

    def delete(self):
        shutil.rmtree(self.path)


def extract_last_layer(container_id: str, layer_path: str) -> Layer:
    layer = None
    tar_path, container_path, manifest_path = '', '', ''

    try:
        client = docker.from_env(timeout=1200)
        container: Container = client.containers.get(container_id)
        container_name = f'test{uuid.uuid4()}'
        container.commit('crawlergpt', container_name)

        tar_path = os.path.join(tempfile.gettempdir(), f"{container_name}.tar")
        image: Image = client.images.get(f'crawlergpt:{container_name}')
        with open(tar_path, 'wb') as f:
            for chunk in image.save():
                f.write(chunk)

        container_path = os.path.join(tempfile.gettempdir(), container_name)
        if not os.path.exists(container_path):
            os.mkdir(container_path)

        with tarfile.open(tar_path, 'r') as tar:
            tar.extract('manifest.json', container_path)
            manifest_path = os.path.join(container_path, 'manifest.json')

            with open(manifest_path, 'r') as f:
                layers = json.loads(f.read())[0]['Layers']
                layer = os.path.dirname(layers[-1])
                tar.extract(os.path.join(layer, 'json'), layer_path)
                tar.extract(os.path.join(layer, 'layer.tar'), layer_path)
                tar.extract(os.path.join(layer, 'VERSION'), layer_path)
                layer = os.path.dirname(layers[-1])
    finally:
        client.images.remove(image=f'crawlergpt:{container_name}')
        if os.path.exists(tar_path):
            os.remove(tar_path)
        if os.path.exists(manifest_path):
            os.remove(manifest_path)
        if os.path.exists(container_path):
            os.rmdir(container_path)

    return Layer(layer, os.path.join(layer_path, layer))


def add_new_layer(image_name: str, layer: Layer, new_image_name: str = None):
    client = docker.from_env(timeout=1200)
    image: Image = client.images.get(image_name)
    temp_extract_path, tar_path, final_tar = '', '', ''

    try:
        tar_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        with open(tar_path, 'wb') as f:
            for chunk in image.save():
                f.write(chunk)

        with tarfile.open(tar_path, 'r') as tar:
            temp_extract_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
            tar.extractall(temp_extract_path)

            manifest_path = os.path.join(temp_extract_path, 'manifest.json')
            with open(manifest_path, 'r') as f:
                manifest = json.loads(f.read())
            manifest[0]['Layers'].append(os.path.join(layer.name, 'layer.tar'))

            with open(manifest_path, 'w') as f:
                f.write(json.dumps(manifest))

            json_path = os.path.join(temp_extract_path, manifest[0]['Config'])
            with open(json_path, 'r') as f:
                json_file = json.loads(f.read())
            layer_digest = hashlib.sha256()
            with open(os.path.join(layer.path, 'layer.tar'), 'rb') as f:
                layer_digest.update(f.read())
            json_file['rootfs']['diff_ids'].append(f"sha256:{layer_digest.hexdigest()}")

            with open(json_path, 'w') as f:
                f.write(json.dumps(json_file))

            shutil.copytree(layer.path, os.path.join(temp_extract_path, layer.name))

            final_tar = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
            with tarfile.open(final_tar, "w") as f_tar:
                for file in os.listdir(temp_extract_path):
                    f_tar.add(os.path.join(temp_extract_path, file), arcname=file)

            with open(final_tar, 'rb') as f:
                image: Image = client.images.load(f.read())[0]
                if new_image_name != None:
                    repository, tag = new_image_name.split(':')
                    image.tag(repository, tag)
    finally:
        if os.path.exists(temp_extract_path):
            shutil.rmtree(temp_extract_path)
        if os.path.exists(tar_path):
            os.remove(tar_path)
        if os.path.exists(final_tar):
            os.remove(final_tar)

@dataclass
class DiffNode:
    children: Dict[str, 'DiffNode']
    kind: int
    path: str
    full_path: str

    @property
    def is_file(self) -> bool:
        return len(self.children) == 0


def extract_diff(container_id: str, diff_file_path: str, ignore_paths=[]):
    save_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    client = docker.from_env(timeout=600)
    container: Container = client.containers.get(container_id)
    
    # Kinds: 0 -> Changed, 1 -> Created, 2 -> Deleted
    diff = container.diff()
    parent_node = DiffNode({}, -1, '/', '/')

    for change in diff:
        if any(map(lambda path: change['Path'].startswith(path), ignore_paths)):
            continue

        # The index removes the empty string from the beggining (/path...)
        path = change['Path'].split(os.sep)[1:]
        current_node = parent_node

        for p in path:
            if p not in current_node.children:
                current_node.children[p] = DiffNode({}, -1, p, '')
            current_node = current_node.children[p]

        current_node.kind = change['Kind']
        current_node.full_path = change['Path']
    
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    
    def handle_node(node: DiffNode):
        for _, child in node.children.items(): 
            if child.kind == 2:
                continue
            elif child.is_file:
                file_path = os.path.join(save_path, child.full_path[1:])
                with open(f'{file_path}.tar', 'wb') as f:
                    bits, _ = container.get_archive(child.full_path)
                    for chunk in bits:
                        f.write(chunk)
                
                with tarfile.open(f'{file_path}.tar', 'r') as f:
                    f.extractall(os.path.dirname(file_path))

                os.remove(f'{file_path}.tar')
            else:
                os.makedirs(os.path.join(save_path, child.full_path[1:]))
            handle_node(child)

    handle_node(parent_node)

    with open(os.path.join(save_path, 'diff.pkl'), 'wb') as f:
        pickle.dump(parent_node, f)
    with tarfile.open(diff_file_path, 'w:gz') as tar_gz:
        tar_gz.add(save_path, arcname="diff")
    
    shutil.rmtree(save_path)


def apply_diff(container_id: str, diff_file_path: str):
    client = docker.from_env(timeout=600)
    container: Container = client.containers.get(container_id)
    diff_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))

    with tarfile.open(diff_file_path, 'r:gz') as tar_gz:
        tar_gz.extractall(diff_path)
    
    with open(os.path.join(diff_path, 'diff', 'diff.pkl'), 'rb') as f:
        parent_node: DiffNode = pickle.load(f)

    def handle_removes(node: DiffNode):
        for _, child in node.children.items():
            handle_removes(child)

        if not node.is_file and node.kind == 2:
            container.exec_run(f'rmdir {node.full_path}')
        elif node.is_file and node.kind == 2:
            container.exec_run(f'rm {node.full_path}')

    for file in os.listdir(os.path.join(diff_path, 'diff')):
        if file != 'diff.pkl':
            random_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
            with tarfile.open(random_path, "w") as tar:
                tar.add(os.path.join(diff_path, 'diff', file), arcname=file)
            with open(random_path, 'rb') as tar:
                container.put_archive('/', tar.read())
            os.remove(random_path)

    handle_removes(parent_node)
    shutil.rmtree(diff_path)


def create_act_image(new_image_name, diff_file_path):
    client = docker.from_env()
    container: Container = client.containers.run('crawlergpt:latest', detach=True)
    apply_diff(container.id, diff_file_path)
    repository, tag = new_image_name.split(':')
    container.commit(repository=repository, tag=tag)
    container.stop()
    container.remove()