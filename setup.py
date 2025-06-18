#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip()
                    and not line.startswith("#")]

setup(
    name="emob-cluster-timeseries",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="E-Mobility Cluster Timeseries Generator for TOP-Energy®",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/emob-cluster-timeseries",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "emob-timeseries=emob_cluster_timeseries:main",
        ],
    },
    keywords="electromobility, timeseries, energy, simulation, csv",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/emob-cluster-timeseries/issues",
        "Source": "https://github.com/yourusername/emob-cluster-timeseries",
        "Documentation": "https://github.com/yourusername/emob-cluster-timeseries#readme",
    },
)
