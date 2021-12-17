from __future__ import absolute_import, print_function

import json
import os
import re

import flask_assetrev
from config import DISABLED, SENTRY_DSN, UNMAINTAINED
from constants import (
    CONTACT_TYPE_EMAIL,
    CONTACT_TYPE_SMS,
    CONTACT_TYPE_YO,
    MAX_SEARCH_RESULTS,
)
from contact import is_valid_yo_name
from dbhelper import db_session
from flask import Flask, g, render_template, request, send_from_directory
from models import Alert, Course, Klass
from raven.contrib.flask import Sentry
from sqlalchemy.sql.expression import or_
from util import (
    contact_type_description,
    klasses_to_template_courses,
    validate_course_id,
)

app = Flask(__name__)
app.config.from_object('config')
flask_assetrev.AssetRev(app)

sentry = Sentry(app, dsn=SENTRY_DSN)


def after_this_request(f):
    if not hasattr(g, 'after_request_callbacks'):
        g.after_request_callbacks = []
    g.after_request_callbacks.append(f)
    return f


@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()


@app.route('/', methods=['GET'])
def homepage():
    @after_this_request
    def add_header(response):
        response.cache_control.no_store = True
        return response

    if UNMAINTAINED:
        return render_template('homepage_unmaintained.html')

    if DISABLED:
        return render_template('homepage_disabled.html')
    return render_template('homepage.html')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static/favicon'),
                               'favicon.ico',
                               mimetype='image/vnd.microsoft.icon')


@app.route('/alert', methods=['GET'])
def show_alert():
    klass_ids = request.args.get('classids', '')
    courses = []

    if klass_ids:
        klass_ids = klass_ids.split(',')
        # filter out all non-numeric ids
        klass_ids = [klass_id for klass_id in klass_ids if re.match(
            r'^\d+$', klass_id)]
        # get course info from db
        klasses = db_session.query(Klass).filter(
            Klass.klass_id.in_(klass_ids)).all()
        courses = klasses_to_template_courses(klasses)

    @after_this_request
    def add_header(response):
        response.cache_control.no_store = True
        return response

    return render_template('alert.html', courses=courses)


@app.route('/api/alerts', methods=['POST'])
def save_alerts():
    # get info from the form
    # if something is invalid or they haven't given a contact or chosen classes
    # just show an error page because they've gotten past the javascript error
    # handling somehow and repopulating the chosen classes list would be super
    # annoying
    # I guess it's still TODO worthy (I'll probably never do it though)
    post_data = request.get_json()

    if not post_data:
        return render_template('error.html',
                               error='Something went wrong')

    if post_data.get('email'):
        contact = post_data['email']
        contact_type = CONTACT_TYPE_EMAIL
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', contact):
            return render_template('error.html',
                                   error='Please enter a valid email address')
    elif post_data.get('phonenumber'):
        contact = re.sub(r'[^0-9+]', '', post_data['phonenumber'])
        contact_type = CONTACT_TYPE_SMS
        if not re.match(r'^(04|\+?614)\d{8}$', contact):
            return render_template('error.html',
                                   error='Please enter a valid Australian ' +
                                         'phone number')
    elif post_data.get('yoname'):
        contact = post_data['yoname'].upper()
        contact_type = CONTACT_TYPE_YO
        if (not re.match(r'^(\d|\w)+$', contact) or
                not is_valid_yo_name(contact)):
            return render_template('error.html',
                                   error='Please enter a valid YO username')
    else:
        return render_template('error.html',
                               error='Please enter some contact info before ' +
                                     'submitting.')

    # get course info from db
    klass_ids = post_data.get('classids', [])
    klasses = db_session.query(Klass).filter(
        Klass.klass_id.in_(klass_ids)).all()
    if not klasses:
        return render_template('error.html',
                               error='Please select at least one class ' +
                                     'before submitting.')

    for klass in klasses:
        alert = Alert(klass_id=klass.klass_id,
                      contact_type=contact_type, contact=contact)
        db_session.add(alert)
    db_session.commit()
    courses = klasses_to_template_courses(klasses)

    return render_template('alert.html',
                           contact_type=contact_type_description(contact_type),
                           contact=contact,
                           courses=courses,
                           success_page=True)


@app.route('/api/courses', methods=['GET'])
def search_courses():
    search_query = '%' + request.args.get('q', '') + '%'
    courses = db_session\
        .query(Course)\
        .filter(or_(Course.name.ilike(search_query),
                    Course.compound_id.ilike(search_query)))\
        .limit(MAX_SEARCH_RESULTS)\
        .all()
    courses = [c.to_dict() for c in courses]
    return json.dumps(courses)


@app.route('/api/courses/<course_id>', methods=['GET'])
def course_info(course_id):
    course_id = course_id.upper()
    dept_id, course_id = validate_course_id(course_id)
    course = db_session.query(Course).filter_by(
        dept_id=dept_id, course_id=course_id).one()
    return json.dumps(course.to_dict(with_classes=True))


@app.route('/api/validateyoname', methods=['GET'])
def validate_yo_name():
    yo_name = request.args.get('yoname', '')
    return json.dumps({'exists': is_valid_yo_name(yo_name)})


@app.after_request
def call_after_request_callbacks(response):
    for callback in getattr(g, 'after_request_callbacks', ()):
        callback(response)

    if not response.cache_control:
        response.cache_control.public = True
        response.cache_control.max_age = 1800

    return response


if __name__ == '__main__':
    app.run()
