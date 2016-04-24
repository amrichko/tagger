from setuptools import setup

def readme():
    with open('README') as f:
        return f.read()

setup(name='simple-tagger',
      version='0.6',
      description='Simple console tool for manage tags on files and directories',
      long_description=readme(),
      url='https://github.com/amrichko/tagger.git',
      classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.5',
        'Topic :: System :: Filesystems',
      ],
      keywords='tag tagger files folders directories',
      author='Andrey Mrichko',
      author_email='andymrk2@gmail.com',
      license='GPLv3',
      py_modules=['tagger'],
      install_requires=[
          'sh',
      ],
      scripts=['bin/tagger', 'bin/lstag', 'bin/lsotag', 'bin/rmtag', 'bin/tag'],
      include_package_data=True,
      zip_safe=False)
