from setuptools import setup, find_namespace_packages

setup(
    name='davo-tools',
    version='0.1.0',
    author='davo',
    author_email='davo.fastcall@gmail.com',
    url='https://github.com/inessa13/davo-tools',
    packages=find_namespace_packages(include=['davo.*']),
    namespace_packages=['davo'],
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
    ],
    entry_points={'console_scripts': [
        'davo-photo = davo.photo.cli:main',
        'davo-vpn = davo.vpn.cli:main',
        'cit = davo.git_tools.cli:main',
    ]},
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development',
        'Topic :: Utilities',
    ],
)
