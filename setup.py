from setuptools import setup
import datetime

YEAR = datetime.date.today().year

__author__ = "Manuel Huber"
__version__ = "0.0.0"
__license__ = "MIT"
__copyright__ = u'%s, Manuel Huber' % YEAR


setup( name = 'shoppingbot'
     , version = __version__
     , description = 'Telegram Bot that manages your shopping list'
     , license = __license__
     , author = __author__
     , author_email = 'Manuel.h87@gmail.com'
     , classifiers = [ "Development Status :: 3 - Alpha"
                     , "License :: OSI Approved :: MIT License"
                     , "Programming Language :: Python :: 3 :: Only"
                     , "Topic :: System :: Systems Administration"
                     ]
     , packages = ['shoppingbot']
     , entry_points = {
           'console_scripts' :
               ['shoppingbot = shoppingbot.__init__:main']
       }
     , install_requires = \
             [ "argparse>=1.4.0"
             , "argcomplete>=1.4.1"
             , "telepot>=10.4"
             , "blessings>=1.6"
             , "tinydb>=3.2.2"
             ]
     )
