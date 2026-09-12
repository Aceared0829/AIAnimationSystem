"""Install the responsibility layout while retaining checkpoint import names."""
from pathlib import Path
from setuptools import find_packages, setup

ROOT = Path(__file__).parent
package_roots = {
    'motionbricks': 'model/motionbricks',
    'motionbricks.data': 'data/runtime',
    'motionbricks.training': 'training/common',
    'motionbricks.vqvae.models': 'training/models/vqvae',
    'motionbricks.motion_backbone.models': 'training/models/backbone',
    'motionbricks.motionlib.train': 'training/common/optim',
    'motionbricks.motion_backbone.inference': 'inference/runtime/backbone',
    'motionbricks.motion_backbone.demo': 'inference/demo',
    'motionbricks.exp_setup': 'inference/runtime/experiment',
    'data': 'data',
    'training': 'training',
    'inference': 'inference',
}
packages = {}
for name, folder in package_roots.items():
    packages[name] = folder
    for child in find_packages(str(ROOT / folder)):
        if name == 'data' and child.startswith('runtime'):
            continue
        if name == 'training' and child.startswith(('models.', 'common')):
            continue
        if name == 'inference' and child.startswith(('demo', 'runtime.backbone', 'runtime.experiment')):
            continue
        packages[f'{name}.{child}'] = f'{folder}/{child.replace(".", "/")}'

setup(
    name='motionbricks', version='0.1.0', python_requires='>=3.10',
    packages=list(packages), package_dir=packages,
    package_data={'data.tools': ['review_web/*']},
    install_requires=['torch>=2.0', 'numpy', 'einops', 'scipy', 'hydra-core', 'omegaconf',
                      'vector-quantize-pytorch', 'colorlog'],
    extras_require={
        'training': ['pytorch-lightning', 'transformers<5', 'adam-atan2-pytorch', 'matplotlib', 'imageio', 'pillow'],
        'demo': ['pytorch-lightning', 'transformers<5', 'adam-atan2-pytorch', 'mujoco>=3.0', 'pynput',
                 "keyboard; platform_system == 'Windows'", "python-xlib; platform_system == 'Linux'"],
    },
)
