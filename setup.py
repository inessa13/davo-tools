from setuptools import setup

setup(
    name='davo-tools',
    version='0.1.0',
    author='davo',
    author_email='davo.fastcall@gmail.com',
    url='https://github.com/inessa13/davo-tools',
    packages=['davo'],
    license='GPLv3',
    python_requires='~=3.0',
    install_requires=[
        'pyyaml',
        'argcomplete',
        'pillow',
        'exif',
        'pyotp',
        'pexpect',
        'pykeepass',
        'keyring',
    ],
    entry_points={'console_scripts': [
        'cit = davo.services.git_tools:main',
        'davo-photo = davo.services.photo.cli:main',
        'davo-tools = davo.cli:main',
    ]},
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Topic :: Utilities',
    ],
)
