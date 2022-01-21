import argparse
import re
import sys
import time
import traceback
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from config import SENTRY_DSN
from constants import CURRENT_TERM, POSTGRES_MAX_INT
from contact import send_alerts
from dbhelper import db_session, get_redis
from models import Alert, Course, Dept, Klass, Timeslot
from tutorifull import app, sentry
from util import (
    hour_of_day_to_seconds_since_midnight,
    web_day_to_int_day,
    web_status_to_db_status,
)


def scrape_course_and_classes(course_id, dept_id, name, klasses):
    '''scrape all the classes in a course'''
    # add the course to the db
    course = Course(course_id=course_id, dept_id=dept_id, name=name)
    db_session.merge(course)

    # remove from this as we find classes, eventually only the classes that are
    # no longer on classutil will appear here
    klasses_to_delete = {klass.klass_id:
                         klass for klass in db_session.query(Klass)
                         .filter_by(course_id=course_id, dept_id=dept_id)
                         .all()}

    # Crappy hack because some course decided to list two classes with the
    # same id...
    klasses_added = set()

    for row in klasses:
        klass_type, _, klass_id, _, status, enrollment, _, time_and_place = (
            d.get_text() for d in row)
        status = web_status_to_db_status(status)
        klass_id = int(klass_id)
        m = re.search(r'(\d+)/(\d+).*', enrollment)
        enrolled = int(m.group(1))
        capacity = int(m.group(2))

        if klass_id in klasses_added:
            continue

        # if this is a new class or the timeslot raw text has changed since we
        # last saw it
        if klass_id not in klasses_to_delete or (
                hash(time_and_place) % POSTGRES_MAX_INT !=
                klasses_to_delete[klass_id].timeslot_raw_string_hash):
            # if the klass already existed, delete all existing timeslots and
            # recreate them
            if klass_id in klasses_to_delete:
                for timeslot in klasses_to_delete[klass_id].timeslots:
                    db_session.delete(timeslot)

            mentioned_times = set()

            for time_and_place_part in time_and_place.split(';'):
                m = re.search(
                    r'(\w+) +(\d+(?::\d+)?(?:-\d+(?::\d+)?)?) *#? ' +
                    r'*(?: *\((?:.*, *)*(.*?)\))?',
                    time_and_place_part)

                if m:
                    day = web_day_to_int_day(m.group(1))

                    time = m.group(2)
                    if '-' in time:
                        start_time, end_time = map(
                            hour_of_day_to_seconds_since_midnight,
                            time.split('-'))
                    else:
                        start_time = hour_of_day_to_seconds_since_midnight(
                            time)
                        end_time = start_time + 60 * 60

                    # only add a timeslot for the first time a specific day/time
                    # is mentioned to avoid situations where
                    # the location changes throughout the semester - we'll only
                    # list the first location
                    if (day, time) not in mentioned_times:
                        mentioned_times.add((day, time))
                        location = m.group(3)
                        # as a last resort, filter out any locations we've
                        # extracted that don't have a letter in them
                        # also filter out anything that looks like a range of
                        # weeks (eg. w1-12)
                        if location is not None and (
                                not re.search(r'[a-zA-Z]', location) or
                                re.match(r'^w\d+(?:-\d+)?$', location)):
                            location = None

                        timeslot = Timeslot(klass_id=klass_id,
                                            day=day,
                                            start_time=start_time,
                                            end_time=end_time,
                                            location=location)
                        db_session.add(timeslot)

        klass = Klass(klass_id=klass_id,
                      course_id=course_id,
                      dept_id=dept_id,
                      klass_type=klass_type,
                      status=status,
                      enrolled=enrolled,
                      capacity=capacity,
                      timeslot_raw_string_hash=(hash(time_and_place) %
                                                POSTGRES_MAX_INT))
        db_session.merge(klass)
        klasses_to_delete.pop(klass_id, None)
        klasses_added.add(klass_id)

    for klass in klasses_to_delete.values():
        db_session.delete(klass)


def scrape_dept(dept_id, name, page):
    '''scrape all the courses in a department'''
    # add the dept to the db
    dept = Dept(dept_id=dept_id, name=name)
    db_session.merge(dept)

    courses_to_delete = {course.compound_id_tuple: course for course in
                         db_session.query(Course).filter_by(dept_id=dept_id)
                         .all()}

    r = requests.get('http://classutil.unsw.edu.au/' + page)
    dept_page = BeautifulSoup(r.text, 'html.parser')
    klasses = []
    course_id = ''
    tables = dept_page.find_all('table')
    if len(tables) < 3:
      return
    for row in tables[2].find_all('tr'):
        data = row.find_all('td')
        if data[0].get('class', [''])[0] == 'cucourse':
            # row is the code and name of a course
            row_course_id = data[0].b.get_text()[4:8]
            if row_course_id == course_id:
                # every now and again we get multiple title rows for the same
                # course
                continue
            if klasses:
                # scrape all the classes from the previous course and empty the
                # array
                courses_to_delete.pop((dept_id, course_id), None)
                scrape_course_and_classes(course_id, dept_id, name, klasses)
                klasses = []
            course_id = row_course_id
            name = data[1].get_text()
        elif (row.get('class', [''])[0] == 'rowHighlight' or
              row.get('class', [''])[0] == 'rowLowlight'):
            # row is info about a class
            klasses.append(data)
    # scrape the classes from the last course
    courses_to_delete.pop((dept_id, course_id), None)
    scrape_course_and_classes(course_id, dept_id, name, klasses)

    for course in courses_to_delete.values():
        db_session.delete(course)

    db_session.commit()


def wait_until_updated():
    # keep checking classutil until it updates
    retry_count = 0
    while True:
        r = requests.get('http://classutil.unsw.edu.au/', stream=True)
        last_time = get_redis().get('last_classutil_update_time')
        if r.headers['Last-Modified'] == last_time:
            retry_count += 1
            if retry_count > 20:
                return False

            time.sleep(10)
            continue

        get_redis().set('last_classutil_update_time',
                        r.headers['Last-Modified'])
        break

    return True


def update_classes(force_update=False):
    if not force_update and not wait_until_updated():
        return

    depts_to_delete = {
        dept.dept_id: dept for dept in db_session.query(Dept).all()}

    r = requests.get('http://classutil.unsw.edu.au/')
    main_page = BeautifulSoup(r.text, 'html.parser')

    # loop through all the departments on the main page
    for row in main_page.find_all('table')[1].find_all('tr'):
        data = row.find_all('td')
        if data[0]['class'][0] == 'cutabhead':
            # row describes the campus of the below departments
            pass
        elif data[0]['class'][0] == 'data':
            # row describes a department
            links = data[:4]
            dept_info = data[4:]
            links = [d.a['href'] if d.a is not None else None for d in links]
            dept_id, name = (d.get_text() for d in dept_info)
            link = links[CURRENT_TERM]
            # check if the department runs in the current semester
            if link is not None:
                depts_to_delete.pop(dept_id, None)
                scrape_dept(dept_id, name, link)

    for dept in depts_to_delete.values():
        db_session.delete(dept)

    db_session.commit()


def check_alerts():
    triggered_alerts = []
    for alert in db_session.query(Alert):
        if alert.should_alert():
            triggered_alerts.append(alert)

    successful_alerts = send_alerts(triggered_alerts)
    for alert in successful_alerts:
        db_session.delete(alert)

    sentry.captureMessage(('Tried to send %d alerts, %d succeeded' %
                           (len(triggered_alerts), len(successful_alerts))),
                          level='info')

    db_session.commit()


if __name__ == '__main__':
    with app.app_context():
        parser = argparse.ArgumentParser()
        parser.add_argument('--no-update', action="store_true",
                            help="don't update the database from classutil")
        parser.add_argument('--no-alert', action="store_true",
                            help="don't send out or delete alerts")
        parser.add_argument('--force-update', action="store_true",
                            help="update the database from classutil even if " +
                                 "it hasn't updated")
        args = parser.parse_args()

        sentry.captureMessage('Starting scraper', level='info')

        try:
            if not args.no_update:
                update_classes(args.force_update)
            if not args.no_alert:
                check_alerts()
        except Exception as e:
            sentry.captureException()
            traceback.print_exc()
