from setuptools import setup

setup(
    name="cross_venv",
    version="0.1",
    packages=['crossenv'],
    package_data = {
        'crossenv' : ['scripts/*.py'],
    },
)


