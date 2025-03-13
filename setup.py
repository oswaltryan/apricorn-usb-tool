import os
from setuptools import setup, find_packages

# Read README for long description if available.
long_description = ''
if os.path.exists('README.md'):
    with open('README.md', encoding='utf-8') as f:
        long_description = f.read()

setup(
    name='win-usb-tool',
    version='0.1.0',
    description='Python wrapper for usbview-cli console application.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Ryan Oswalt',
    author_email='your.email@example.com',
    url='',
    packages=find_packages(),
    python_requires='==3.12.*',
    install_requires=[
        'pywin32==309',  # Dependency locked to pywin32 version 309
    ],
    # Include the executable in the package.
    package_data={
        'windows_usb': ['utils/usbdeview.exe'],
    },
    include_package_data=True,
    entry_points={
        'console_scripts': [
            # Creates a globally available CLI command 'usb'
            'usb=windows_usb:main',
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3.12',
        'Operating System :: Microsoft :: Windows',
        'License :: OSI Approved :: MIT License',
    ],
)
