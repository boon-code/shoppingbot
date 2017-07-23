from setuptools import setup
import datetime
import sys

YEAR = datetime.date.today().year

__author__ = "Manuel Huber"
__license__ = "MIT"
__copyright__ = u'%s, Manuel Huber' % YEAR

install_requires = [ "argcomplete>=1.4.1"
                   , "telepot>=10.4"
                   , "blessings>=1.6"
                   , "tinydb>=3.2.2"
                   ]

if sys.version_info < (2, 7):
    install_requires.append("argparse>=1.4.0")


setup( name = 'shoppingbot'
     , version_format = "{tag}.{commitcount}+{gitsha}"
     , description = 'Telegram Bot that manages your shopping list'
     , license = __license__
     , author = __author__
     , author_email = 'Manuel.h87@gmail.com'
     , classifiers = [ "Development Status :: 3 - Alpha"
                     , "License :: OSI Approved :: MIT License"
                     , "Programming Language :: Python :: 3 :: Only"
                     , "Topic :: System :: Systems Administration"
                     ]
     , setup_requires = ["setuptools-git-version"]
     , packages = ['shoppingbot']
     , entry_points = {
           'console_scripts' :
               ['shoppingbot = shoppingbot.__init__:main']
       }
     , install_requires = install_requires
     )
