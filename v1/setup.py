from setuptools import setup, find_packages

setup(
    name="dvmdash",
    version="0.1.0",
    author="Dustin Dannenhauer",
    author_email="",
    description="A dashboard for DVM activity on Nostr",
    packages=find_packages(),
    install_requires=[
        # Add any dependencies your project requires
        # For example: 'requests', 'numpy', 'pandas'
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
    ],
)
