import json
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from subprocess import PIPE, Popen

import requests
from config import (
    BASE_DOMAIN_NAME,
    FULL_DOMAIN_NAME,
    MAILGUN_API_KEY,
    MAILGUN_DOMAIN_NAME,
    TELSTRA_CONSUMER_KEY,
    TELSTRA_CONSUMER_SECRET,
    YO_API_KEY,
)
from constants import CONTACT_TYPE_EMAIL, CONTACT_TYPE_SMS, CONTACT_TYPE_YO
from dbhelper import get_redis
from flask import render_template
from util import chunks, klasses_to_template_courses


def send_alerts(alerts):
    from tutorifull import sentry

    # organizes the alerts by contact info then sends one alert per contact info
    alerts_by_contact = defaultdict(list)
    successful_alerts = []

    for alert in alerts:
        alerts_by_contact[(alert.contact, alert.contact_type)].append(alert)

    for contact, alerts in alerts_by_contact.iteritems():
        contact, contact_type = contact
        try:
            if contact_type == CONTACT_TYPE_EMAIL:
                alert_by_email(contact, alerts)
            elif contact_type == CONTACT_TYPE_SMS:
                alert_by_sms(contact, alerts)
            elif contact_type == CONTACT_TYPE_YO:
                alert_by_yo(contact, alerts)
            successful_alerts += alerts
        except Exception:
            sentry.captureException()

    return successful_alerts


def create_alert_link(klass_ids):
    return ('https://' + FULL_DOMAIN_NAME + '/alert?classids=' +
            ','.join(map(str, klass_ids)))


def klass_to_text_email_line(klass):
    line = ' - '
    line += '%s | ' % klass['type']
    line += '%s | ' % (', '.join('%s %s-%s' % (timeslot['day'],
                                               timeslot['start_time'],
                                               timeslot['end_time'])
                                 for timeslot in klass['timeslots']))
    line += '%s | ' % ', '.join(timeslot['location']
                                for timeslot in klass['timeslots'])
    line += '%s | ' % klass['status']
    line += '%d/%d\n' % (klass['enrolled'], klass['capacity'])
    return line


def alert_by_email(email, alerts):
    courses = klasses_to_template_courses(alert.klass for alert in alerts)

    text = '''
These classes now have a space for you to enrol.

%s


Made By a Dome
''' % ''.join(course['course_id'] + '\n' +
              ''.join(klass_to_text_email_line(klass)
                      for klass in course['classes'])
              for course in courses)
    html = render_template('email.html', courses=courses)

    r = requests.post('https://api.mailgun.net/v3/' + MAILGUN_DOMAIN_NAME +
                      '/messages',
                      auth=('api', MAILGUN_API_KEY),
                      data={'from': 'Tutorifull <tutorifull@'
                            + BASE_DOMAIN_NAME + '>',
                            'to': email,
                            'subject': 'A spot has opened up in a class!',
                            'text': text,
                            'html': html})

    assert r.status_code == 200


def alert_by_sms(phone_number, alerts):
    # send alerts in batches of 10 classes to avoid going over the 160 char
    # limit
    for alerts_chunk in chunks(alerts, 10):
        send_sms(phone_number,
                 "A spot has opened up in a class: %s" % create_alert_link(
                     a.klass.klass_id for a in alerts_chunk))


def get_telstra_api_access_token():
    access_token = get_redis().get('telstra_api_access_token')
    if access_token is not None:
        return access_token

    r = requests.post('https://tapi.telstra.com/v2/oauth/token',
                      data={
                          'client_id': TELSTRA_CONSUMER_KEY,
                          'client_secret': TELSTRA_CONSUMER_SECRET,
                          'grant_type': 'client_credentials'
                      }).json()

    # cache the access token in redis, making it expire slightly earlier than it
    # does on the Telstra server
    get_redis().setex('telstra_api_access_token', int(
        r['expires_in']) - 60, r['access_token'])
    return r['access_token']


def send_sms(phone_number, message):
    access_token = get_telstra_api_access_token()
    r = requests.post('https://tapi.telstra.com/v2/messages/sms',
                      headers={'Authorization': 'Bearer %s' % access_token,
                               'Content-Type': 'application/json'},
                      data=json.dumps({
                          'to': phone_number,
                          'body': message
                      }))
    assert r.status_code == 201, (
        'While sending an sms, Telstra api returned status code %d' %
        r.status_code)


def alert_by_yo(username, alerts):
    send_yo(username,
            create_alert_link(a.klass.klass_id for a in alerts),
            'A spot has opened up in a class!')


def send_yo(username, link=None, text=None):
    r = requests.post("https://api.justyo.co/yo/",
                      data={'api_token': YO_API_KEY,
                            'username': username,
                            'link': link,
                            'text': text})

    # either we succeed to send the yo, or the username doesn't exist - either
    # way we want the alerts to be deleted
    assert r.status_code == 200 or r.status_code == 404, (
        'While sending a yo, yo api returned status code %d' %
        r.status_code)


def is_valid_yo_name(yo_name):
    r = requests.get('https://api.justyo.co/check_username/',
                     params={'api_token': YO_API_KEY,
                             'username': yo_name}).json()
    return r['exists']
