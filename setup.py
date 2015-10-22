from setuptools import setup

# see https://github.com/GaretJax/i18n-utils/blob/master/setup.py
# and https://github.com/elastic/curator/blob/master/setup.py
setup(
    name='http-booster',
    version='0.1',
    url='https://github.com/polyrabbit/http-booster',
    license='MIT',
    author='poly',
    author_email='mcx_221@foxmail.com',
    description='A multi-threaded proxy',
    platforms='any',
    install_requires=open('./requirements.txt').read().split('\n'),
    entry_points={
        "console_scripts": ["httpBooster=httpBooster:main"]
    }
)
