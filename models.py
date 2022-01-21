from constants import STATUS_OPEN
from dbhelper import Base
from sqlalchemy import Column, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import column_property, relationship


class Alert(Base):
    '''An alert that notifies the given contact information when the class has
    an empty space'''
    __tablename__ = 'alerts'

    alert_id = Column(Integer, primary_key=True)
    klass_id = Column(Integer, ForeignKey('klasses.klass_id'), nullable=False)
    contact_type = Column(Integer, nullable=False)
    contact = Column(String, nullable=False)

    klass = relationship('Klass', back_populates='alerts')

    def __repr__(self):
        return ("<Alert(alert_id='%d', klass_id='%d', contact_type='%s', " +
                "contact='%s')>" % (self.alert_id, self.klass_id,
                                    self.contact_type, self.contact))

    def should_alert(self):
        if (self.klass.status == STATUS_OPEN and
                self.klass.enrolled < self.klass.capacity):
            return True
        return False


class Dept(Base):
    '''A department eg. COMP'''
    __tablename__ = 'depts'
    dept_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)

    courses = relationship('Course', order_by='Course.course_id',
                           back_populates='dept',
                           cascade="all, delete, delete-orphan")

    def __repr__(self):
        return "<Dept(dept_id='%s', name='%s')>" % (self.dept_id, self.name)


class Course(Base):
    '''A course eg. COMP2041'''
    __tablename__ = 'courses'
    course_id = Column(String, primary_key=True)
    dept_id = Column(String, ForeignKey('depts.dept_id'), primary_key=True)
    name = Column(String, nullable=False)

    dept = relationship('Dept', back_populates='courses')
    klasses = relationship('Klass', back_populates='course',
                           cascade="all, delete, delete-orphan")

    compound_id = column_property(dept_id + course_id)

    def __repr__(self):
        return "<Course(dept_id='%s, 'course_id='%s', name='%s')>" % (
            self.dept_id, self.course_id, self.name)

    @property
    def compound_id_tuple(self):
        return (self.dept_id, self.course_id)

    def to_dict(self, with_classes=False):

        def sort_key(c):
            return (c.klass_type,
                    c.timeslots[0].day if c.timeslots else None,
                    c.timeslots[0].start_time if c.timeslots else None)

        d = {'course_id': self.compound_id,
             'course_name': self.name}
        if with_classes:
            d['classes'] = [klass.to_dict()
                            for klass in sorted(self.klasses,
                                                key=sort_key)]
        return d


class Klass(Base):
    '''A class you can choose when you are enrolling
    (a lab, a series of lectures, etc.)'''
    __tablename__ = 'klasses'
    klass_id = Column(Integer, primary_key=True)
    course_id = Column(String, nullable=False)
    dept_id = Column(String, nullable=False)
    klass_type = Column(String, nullable=False)  # LEC/LAB/TUT etc.
    status = Column(Integer, nullable=False)
    enrolled = Column(Integer, nullable=False)
    capacity = Column(Integer, nullable=False)
    # to check whether we need to update the timeslots
    timeslot_raw_string_hash = Column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ['course_id', 'dept_id'],
            ['courses.course_id', 'courses.dept_id'],
            name="fk_course"
        ),
    )

    timeslots = relationship('Timeslot', back_populates='klass',
                             cascade="all, delete, delete-orphan")
    course = relationship('Course', back_populates='klasses')
    alerts = relationship('Alert', order_by='Alert.alert_id',
                          back_populates='klass',
                          cascade="all, delete, delete-orphan")

    def __repr__(self):
        return ("<Klass(klass_id='%d', dept_id='%s', course_id='%s', " +
                "klass_type='%s')>" % (self.klass_id, self.dept_id,
                                       self.course_id, self.klass_type))

    def to_dict(self):
        from util import db_status_to_text_status

        if self.capacity == 0:
            percentage = 0
        else:
            percentage = int((float(self.enrolled) / self.capacity) * 100)

        return {'class_id': self.klass_id,
                'type': self.klass_type,
                'timeslots': [timeslot.to_dict()
                              for timeslot in self.timeslots],
                'status': db_status_to_text_status(self.status),
                'enrolled': self.enrolled,
                'capacity': self.capacity,
                'percentage': percentage}


class Timeslot(Base):
    __tablename__ = 'timeslots'
    timeslot_id = Column(Integer, primary_key=True)
    klass_id = Column(Integer, ForeignKey('klasses.klass_id'), nullable=False)
    day = Column(Integer)
    start_time = Column(Integer)
    end_time = Column(Integer)
    location = Column(String)

    def __repr__(self):
        from util import (
            int_day_to_text_day,
            seconds_since_midnight_to_hour_of_day,
        )

        return ("<Timeslot(day='%d', start_time='%d', end_time='%s', " +
                "location='%s')>" % (int_day_to_text_day(self.day),
                                     seconds_since_midnight_to_hour_of_day(
                    self.start_time),
                    seconds_since_midnight_to_hour_of_day(
                    self.end_time),
                    self.location))

    def to_dict(self):
        from util import (
            int_day_to_text_day,
            seconds_since_midnight_to_hour_of_day,
        )

        return {'day': int_day_to_text_day(self.day),
                'start_time': seconds_since_midnight_to_hour_of_day(
                    self.start_time),
                'end_time': seconds_since_midnight_to_hour_of_day(
                    self.end_time),
                'location': self.location}

    klass = relationship('Klass', back_populates='timeslots')
