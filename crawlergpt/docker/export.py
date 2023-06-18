import os
import shutil
import uuid
import tempfile
import json
import docker
import tarfile
from dataclasses import dataclass

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
            manifest = os.path.join(container_path, 'manifest.json')

            with open(manifest, 'r') as f:
                layers = json.loads(f.read())[0]['Layers']
                tar.extract(layers[-1], layer_path)
                layer = os.path.dirname(layers[-1])
    finally:
        client.images.remove(image=f'crawlergpt:{container_name}')
        if os.path.exists(tar_path):
            os.remove(tar_path)
        if os.path.exists(os.path.join(container_path, 'manifest.json')):
            os.remove(os.path.join(container_path, 'manifest.json'))
        if os.path.exists(container_path):
            os.rmdir(container_path)

    return Layer(layer, os.path.join(layer_path, layer))

def add_new_layer(image_name: str, layer: Layer):
    client = docker.from_env(timeout=1200)
    image: Image = client.images.get(image_name)

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
        manifest[0]['Layers'].append(layer.name)

        with open(manifest_path, 'w') as f:
            f.write(json.dumps(manifest))

        shutil.copytree(layer.path, os.path.join(temp_extract_path, layer.name))

        final_tar = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        with tarfile.open(final_tar, "w") as f_tar:
            f_tar.add(temp_extract_path, arcname=os.path.basename(temp_extract_path))

        with open(final_tar, 'rb') as f:
            client.images.load(f.read())
        
    #shutil.rmtree(temp_extract_path)
    #os.remove(tar_path)

layer = extract_last_layer('8b74bae099c2', '.')
add_new_layer("glitch:latest", layer)
layer.delete()