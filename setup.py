import os
from setuptools import setup, find_packages

def read(fname):
    try:
        return open(os.path.join(os.path.dirname(__file__), fname)).read()
    except FileNotFoundError:
        return "AML End-to-End Detection System"

setup(
    name="aml_end_to_end",
    version="1.0.0",
    description="Graph-based Anti-Money Laundering Detection using Node2Vec and Autoencoder",
    author="AML Team",
    license="Apache License 2.0",
    keywords="AML, Anti-Money Laundering, Graph Neural Network, Node2Vec, Anomaly Detection, Machine Learning",
    url="https://github.com/logicalclocks/AMLend2end.git",
    # Original work by Logical Clocks AB - https://github.com/logicalclocks/AMLend2end
    packages=find_packages(),
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    python_requires=">=3.10",
    install_requires=[
        # Core ML/Data
        "tensorflow>=2.15.0",
        "numpy>=1.24.0",
        "pandas>=2.0.0",
        "scikit-learn>=1.3.0",

        # Graph processing
        "networkx>=3.0",
        "node2vec>=0.4.6",

        # Visualization
        "matplotlib>=3.7.0",
        "seaborn>=0.13.0",

        # Data storage
        "pyarrow>=14.0.0",

        # Jupyter support
        "ipywidgets>=8.0.0",
        "jupyterlab>=4.0.0",

        # Utilities
        "scipy>=1.10.0",
        "tqdm>=4.65.0",
    ],
    extras_require={
        "gpu": [
            "nvidia-cudnn-cu12>=9.3.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Office/Business :: Financial",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Intended Audience :: Developers",
        "Intended Audience :: Financial and Insurance Industry",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
            "aml-detect=adversarialaml.cli:main",
        ],
    },
)
