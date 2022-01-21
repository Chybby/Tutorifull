import requests
from bs4 import BeautifulSoup

log = open('classutil_update.log', 'a')

r = requests.get('http://classutil.unsw.edu.au/')
log.write('Date from headers: %s\n' % r.headers['Date'])
log.write('Last-Modified from headers: %s\n' % r.headers['Last-Modified'])
main_page = BeautifulSoup(r.text, 'html.parser')
log.write('Last-Modified from page: %s\n\n' % main_page.body.p.b.text)

log.close()
