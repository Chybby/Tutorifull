'''
This is an example config file
copy this into a file called 'config.py' and change values to ones specific to you
'''

# how to connect to the database
DATABASE = 'postgresql://tutorifull:tutorifull@localhost:5432/tutorifull'
REDIS_PORT = 6379
DEBUG = False  # never set this to True in production
SECRET_KEY = 'example secret key'  # flask secret key
BASE_DOMAIN_NAME = 'example.com'  # base domain name hosting the site
SUB_DOMAIN_NAME = 'test'  # sub domain name hosting the site
FULL_DOMAIN_NAME = SUB_DOMAIN_NAME + '.' + \
    BASE_DOMAIN_NAME  # full domain name hosting the site
DISABLED = True  # Whether to show the enabled or disabled homepage
UNMAINTAINED = False  # Whether to show the unmaintained homepage
MAILGUN_DOMAIN_NAME = 'mg.example.com'  # domain for sending mailgun emails
YO_API_KEY = 'example YO api key'  # YO api key
MAILGUN_API_KEY = 'example Mailgun api key'  # Mailgun api key
TELSTRA_CONSUMER_KEY = 'example telstra consumer key'  # Telstra consumer key
TELSTRA_CONSUMER_SECRET = 'example telstra consumer secret'  # Telstra consumer secret
# sentry.io DSN, for error logging
SENTRY_DSN = 'https://1234567890:1234567890@sentry.io/1234567890'
# Manifest file for content hashed static files (for cache busting)
ASSETREV_MANIFEST_FILE = 'manifest.json'
