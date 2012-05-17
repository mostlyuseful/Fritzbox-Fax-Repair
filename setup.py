# -*- coding: utf-8 -*-

from distutils.core import setup

setup(name="fboxfaxrepair",
      version="0.1",
      author="Maurice-Pascal Sonnemann",
      author_email="msonnemann@online.de",
      url="http://pypi.python.org/pypi/fboxfaxrepair",
      description="Repairs invalid PDF files as they are sometimes created by Fritz!Box fax machines",
      classifiers=["Development Status :: 3 - Alpha",
                   "Environment :: Console",
                   "Intended Audience :: Developers",
                   "Intended Audience :: End Users/Desktop",
                   "License :: OSI Approved :: MIT License",
                   "Natural Language :: English",
                   "Operating System :: POSIX :: Linux",
                   "Programming Language :: Python :: 2",
                   "Topic :: Communications :: Fax",
                   "Topic :: Office/Business",
                   "Topic :: Software Development :: Libraries :: Python Modules",
                   "Topic :: Utilities"],
      py_modules=["fboxfaxrepair"])
