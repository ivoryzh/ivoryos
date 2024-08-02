from setuptools import setup, find_packages

setup(
    name='ivoryOS',
    version='0.1.0',
    packages=find_packages(),
    include_package_data=True,
    description='an open-source Python package enabling Self-Driving Labs (SDLs) interoperability',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Ivory Zhang',
    author_email='ivoryzhang@chem.ubc.ca',
    license='MIT',
    install_requires=[
        "ax-platform",
        "bcrypt",
        "Flask-Login",
        "Flask-Session",
        "Flask-SocketIO",
        "Flask-SQLAlchemy",
        "Flask-WTF",
        "mysqlclient==2.1.1",
        "SQLAlchemy-Utils",
        "openai",
        "python-dotenv",
    ],
    url='https://gitlab.com/heingroup/ivoryos'
)
