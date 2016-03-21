from __future__ import (
    absolute_import,
    print_function,
)

import re

from flask import g
from sqlalchemy.sql import exists

from constants import (
    CONTACT_TYPE_EMAIL,
    CONTACT_TYPE_SMS,
    CONTACT_TYPE_YO,
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_FULL,
    STATUS_OPEN,
    STATUS_STOPPED,
    STATUS_TENTATIVE,
)
from models import Klass

web_status_to_db_status_dict = {'open': STATUS_OPEN,
                                'full': STATUS_FULL,
                                'clos': STATUS_CLOSED,
                                'tent': STATUS_TENTATIVE,
                                'canc': STATUS_CANCELLED,
                                'stop': STATUS_STOPPED}


def web_status_to_db_status(status):
    return web_status_to_db_status_dict[status[:4].lower()]

db_status_to_text_status_dict = {STATUS_OPEN: 'Open',
                                 STATUS_FULL: 'Full',
                                 STATUS_CLOSED: 'Closed',
                                 STATUS_TENTATIVE: 'Tentative',
                                 STATUS_CANCELLED: 'Cancelled',
                                 STATUS_STOPPED: 'Stopped'}


def db_status_to_text_status(status):
    return db_status_to_text_status_dict[status]


web_day_to_int_day_dict = {'mon': 0,
                           'tue': 1,
                           'wed': 2,
                           'thu': 3,
                           'fri': 4,
                           'sat': 5,
                           'sun': 6}


def web_day_to_int_day(day):
    return web_day_to_int_day_dict[day.lower()]

int_day_to_text_day_dict = {0: 'Mon',
                            1: 'Tue',
                            2: 'Wed',
                            3: 'Thu',
                            4: 'Fri',
                            5: 'Sat',
                            6: 'Sun'}


def int_day_to_text_day(day):
    if day is None:
        return None
    return int_day_to_text_day_dict[day]


def hour_of_day_to_seconds_since_midnight(hour):
    hour = hour.split(':')
    seconds = int(hour[0]) * 60 * 60
    if len(hour) == 2:
        seconds += int(hour[1]) * 60

    return seconds


def seconds_since_midnight_to_hour_of_day(seconds):
    if seconds is None:
        return None

    hour = seconds / 60.0 / 60.0
    if hour % 1 == 0.5:
        hour = str(int(hour)) + ':30'
    else:
        hour = str(int(hour))
    return hour


def contact_type_description(contact_type):
    pretty_contact_type = {CONTACT_TYPE_EMAIL: 'an email', CONTACT_TYPE_SMS: 'an SMS', CONTACT_TYPE_YO: 'a YO'}
    return pretty_contact_type[contact_type]


def validate_klass_id(klass_id):
    klass_id = int(klass_id)
    if not g.db.query(exists().where(Klass.klass_id == klass_id)).scalar():
        raise KeyError
    return klass_id


def validate_course_id(course_id):
    if re.match(r'^[A-Z]{4}[0-9]{4}$', course_id):
        return course_id[:4], course_id[4:]
    else:
        raise Exception