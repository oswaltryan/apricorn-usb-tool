import os
from setuptools import setup, find_packages

# Read README for long description if available
long_description = ""
if os.path.exists("README.md"):
    with open("README.md", encoding="utf-8") as f:
        long_description = f.read()

setup(
    name='win-usb-tool',  
    version='0.1.2',
    description='Cross-platform USB tool with no Linux deps, Windows libusb + WMI on Windows only.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Ryan Oswalt',
    author_email='your.email@example.com',
    url='',  # e.g., your GitHub repo
    packages=find_packages(),
    python_requires='>=3.9',

    # -------------------------------
    # Only install Windows deps on Windows
    # -------------------------------
    install_requires=[
        'pywin32==309; platform_system=="Windows"',
        'libusb==1.0.27.post4; platform_system=="Windows"',
        'pygments==2.19.1; platform_system=="Windows"',
        # ^ If needed on Windows only
    ],
    setup_requires=['setuptools>=75.8.0'],

    # This includes all package data from MANIFEST.in or in the package dir
    include_package_data=True,

    # ---------------------------------------
    # Single console entry point: "usb"
    # ---------------------------------------
    entry_points={
        'console_scripts': [
            # When user types "usb", we call "usb_tool.cross_usb:main"
            'usb=usb_tool.cross_usb:main',
        ],
    },

    classifiers=[
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
        'License :: OSI Approved :: MIT License',
    ],
)
