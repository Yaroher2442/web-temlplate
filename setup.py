from distutils.core import setup

DEPTH = 20

setup(
    name='web-foundation',
    packages=['web_foundation'],
    package_data={
        'web_foundation': [('*/' * i).rstrip("/") for i in range(1, DEPTH)],
    },
    version='0.2.44',
    license='MIT',
    description='Python web template to http apps (web-foundation)',
    author='Yaroha',
    author_email='yaroher2442@gmail.com',
    keywords=['SOME', 'MEANINGFULL', 'KEYWORDS'],
    install_requires=[
        "sanic==22.9.1",
        "sanic-ext==22.9.1",
        "tortoise-orm==0.19.1",
        "asyncpg==0.26.0",
        "pydantic==1.10.2",
        "orjson==3.8.0",
        "apscheduler==3.9.1",
    ],
    classifiers=[
        'Development Status :: 44 - Alpha',
    ],
    extras_require={
        "aerich": ["aerich==0.7.3"],
        "prometheus": ["prometheus-client==0.14.1"],
    }
)
