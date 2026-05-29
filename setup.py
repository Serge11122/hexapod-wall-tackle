from setuptools import setup, find_packages

setup(
    name="hexapod_sim",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["numpy", "Pillow", "matplotlib", "scipy"],
)
