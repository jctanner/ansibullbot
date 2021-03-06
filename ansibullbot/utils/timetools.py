#!/usr/bin/env python

import datetime
import logging
from github import GithubObject


def timeobj_from_timestamp(timestamp):
    """Parse a timestamp with pygithub"""
    dt = GithubObject.GithubObject._makeDatetimeAttribute(timestamp)
    return dt.value


def strip_time_safely(tstring):
    """Try various formats to strip the time from a string"""
    res = None
    tsformats = (
        u'%Y-%m-%dT%H:%M:%SZ',
        u'%Y-%m-%dT%H:%M:%S.%f',
        u'%Y-%m-%dT%H:%M:%S',
    )
    for tsformat in tsformats:
        try:
            res = datetime.datetime.strptime(tstring, tsformat)
            break
        except Exception:
            pass
    if res is None:
        logging.error(u'{} could not be stripped'.format(tstring))
        raise Exception(u'{} could not be stripped'.format(tstring))
    return res
