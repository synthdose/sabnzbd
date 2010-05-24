#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
sabnzbd.rss - rss client functionality
"""

import re
import logging
import time
import threading

import sabnzbd
from sabnzbd.constants import *
from sabnzbd.decorators import synchronized
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.misc import cat_convert, sanitize_foldername, wildcard_to_re
import sabnzbd.emailer as emailer
from sabnzbd.encoding import latin1, unicoder

import sabnzbd.utils.feedparser as feedparser
from sabnzbd.lang import T, Ta

__RSS = None  # Global pointer to RSS-scanner instance


################################################################################
# Wrapper functions                                                            #
################################################################################

def init():
    global __RSS
    __RSS = RSSQueue()

def stop():
    global __RSS
    if __RSS:
        __RSS.stop()
        try:
            __RSS.join()
        except:
            pass

def del_feed(feed):
    global __RSS
    if __RSS: __RSS.delete(feed)

def run_feed(feed, download, ignoreFirst=False, force=False):
    global __RSS
    if __RSS: return __RSS.run_feed(feed, download, ignoreFirst, force=force)

def show_result(feed):
    global __RSS
    if __RSS: return __RSS.show_result(feed)

def flag_downloaded(feed, id):
    global __RSS
    if __RSS: __RSS.flag_downloaded(feed, id)

def run_method():
    global __RSS
    if __RSS:
        return __RSS.run()
    else:
        return None

def save():
    global __RSS
    if __RSS: __RSS.save()

def clear_feed(feed):
    global __RSS
    if __RSS: __RSS.clear_feed(feed)

################################################################################

def notdefault(item):
    """ Return True if not None/"None"/"Default"/""
    """
    return bool(item) and item.lower() not in ('default', 'none')


def ListUris():
    """ Return list of all RSS uris """
    uris = []
    for uri in config.get_rss():
        uris.append(uri)
    return uris

def convert_filter(text):
    """ Return compiled regex.
        If string starts with re: it's a real regex
        else quote all regex specials, replace '*' by '.*'
    """
    if text[:3].lower() == 're:':
        txt = text[3:]
    else:
        txt = wildcard_to_re(text)
    try:
        return re.compile(txt, re.I)
    except:
        logging.error(Ta('error-rssRegex@1'), text)
        return None


LOCK = threading.RLock()
class RSSQueue(object):
    def __init__(self):
        self.jobs = {}
        try:
            feeds = sabnzbd.load_admin(RSS_FILE_NAME)
            if type(feeds) == type({}):
                for feed in feeds:
                    self.jobs[feed] = {}
                    for link in feeds[feed]:
                        data = feeds[feed][link]
                        if type(data) == type([]):
                            # Convert previous list-based store to dictionary
                            new = {}
                            try:
                                new['status'] = data[0]
                                new['title'] = data[1]
                                new['url'] = data[2]
                                new['cat'] = data[3]
                                new['pp'] = data[4]
                                new['script'] = data[5]
                                new['time'] = data[6]
                                new['prio'] = str(NORMAL_PRIORITY)
                                self.jobs[feed][link] = new
                            except IndexError:
                                del new
                        else:
                            self.jobs[feed][link] = feeds[feed][link]
        except IOError:
            pass
        # jobs is a NAME-indexed dictionary
        #    Each element is link-indexed dictionary
        #        Each element is another dictionary:
        #           status : 'D', 'G', 'B', 'X' (downloaded, good-match, bad-match, obsolete)
        #               '*' added means: from the initial batch
        #           title : Title
        #           url : URL or MsgId
        #           cat : category
        #           pp : pp
        #           script : script
        #           prio : priority
        #           time : timestamp (used for time-based clean-up)
        #           order : order in the RSS feed

        self.shutdown = False
        self.__running = False

    def stop(self):
        self.shutdown = True

    @synchronized(LOCK)
    def run_feed(self, feed=None, download=False, ignoreFirst=False, force=False):
        """ Run the query for one URI and apply filters """
        self.shutdown = False

        def dup_title(title):
            title = title.lower()
            for fd in self.jobs:
                for lk in self.jobs[fd]:
                    item = self.jobs[fd][lk]
                    if item.get('status', ' ')[0] == 'D' and \
                       item.get('title', '').lower() == title:
                        return True
            return False


        if not feed:
            return 'No such feed'

        newlinks = []
        new_downloads = []

        # Preparations, get options
        try:
            feeds = config.get_rss()[feed]
        except KeyError:
            logging.error(Ta('error-rssBadFeed@1'), feed)
            logging.debug("Traceback: ", exc_info = True)
            return T('error-rssBadFeed@1') % feed

        uri = feeds.uri()
        defCat = feeds.cat()
        if defCat == "":
            defCat = None
        defPP = feeds.pp()
        defScript = feeds.script()
        defPriority = feeds.priority()

        # Preparations, convert filters to regex's
        regexes = []
        reTypes = []
        reCats = []
        rePPs = []
        reScripts = []
        for filter in feeds.filters():
            reCat = filter[0]
            if not reCat:
                reCat = None
            reCats.append(reCat)
            rePPs.append(filter[1])
            reScripts.append(filter[2])
            reTypes.append(filter[3])
            regexes.append(convert_filter(filter[4]))
        regcount = len(regexes)

        # Set first if this is the very first scan of this URI
        first = feed not in self.jobs
        if first:
            self.jobs[feed] = {}

        jobs = self.jobs[feed]

        first = first and ignoreFirst

        # Add sabnzbd's custom User Agent
        feedparser.USER_AGENT = 'SABnzbd+/%s' % sabnzbd.version.__version__

        # Check for nzbs.org
        if 'nzbs.org/' in uri and not ('&dl=1' in uri):
            uri += '&dl=1'

        # Read the RSS feed
        logging.debug("Running feedparser on %s", uri)
        d = feedparser.parse(uri.replace('feed://', 'http://'))
        logging.debug("Done parsing %s", uri)
        if not d:
            logging.info(Ta('warn-failRSS@1'), uri)
            return T('warn-failRSS@1') % uri

        entries = d.get('entries')
        if 'bozo_exception' in d and not entries:
            logging.info(Ta('warn-failRSS@2'), uri, str(d['bozo_exception']))
            return T('warn-failRSS@2') % (uri, str(d['bozo_exception']))
        if not entries:
            logging.info('RSS Feed was empty: %s', uri)
            return ''

        order = 0
        # Filter out valid new links
        for entry in entries:
            if self.shutdown: return

            try:
                link, category = _get_link(uri, entry)
            except (AttributeError, IndexError):
                link = None
                category = ''
                logging.error('Incompatible feed %s', uri)
                logging.debug("Traceback: ", exc_info = True)
                return 'Incompatible feed'
            category = latin1(category)

            if link:
                # Make sure there are no spaces in the URL
                link = link.replace(' ','')

                # Make sure only latin-1 encodable characters occur
                atitle = latin1(entry.title)
                title = unicoder(atitle)

                newlinks.append(link)

                if cfg.no_dupes() and dup_title(title):
                    logging.info("Ignoring duplicate job %s", atitle)
                    continue

                myCat = defCat
                myPP = ''
                myScript = ''
                #myPriority = 0

                if (link not in jobs) or (jobs[link].get('status', ' ') in ('G', 'B', 'G*', 'B*')):
                    # Match this title against all filters
                    logging.debug('Trying title %s', atitle)
                    result = False
                    for n in xrange(regcount):
                        if notdefault(reCats[n]):
                            myCat = reCats[n]
                        elif category:
                            myCat = cat_convert(category)
                        else:
                            myCat = defCat
                        if notdefault(rePPs[n]):
                            myPP = rePPs[n]
                        elif not (reCats[n] or category):
                            myPP = defPP
                        if notdefault(reScripts[n]):
                            myScript = reScripts[n]
                        elif not (notdefault(reCats[n]) or category):
                            myScript = defScript

                        if category and reTypes[n]=='C':
                            found = re.search(regexes[n], category)
                            if not found:
                                logging.debug("Filter rejected on rule %d", n)
                                result = False
                                break
                        else:
                            found = re.search(regexes[n], title)
                            if reTypes[n]=='M' and not found:
                                logging.debug("Filter rejected on rule %d", n)
                                result = False
                                break
                            if found and reTypes[n]=='A':
                                logging.debug("Filter matched on rule %d", n)
                                result = True
                                break
                            if found and reTypes[n]=='R':
                                logging.debug("Filter rejected on rule %d", n)
                                result = False
                                break

                    act = download and not first
                    if link in jobs:
                        act = act and not jobs[link].get('status', '').endswith('*')
                        act = act or force
                        star = first or jobs[link].get('status', '').endswith('*')
                    else:
                        star = first
                    if result:
                        _HandleLink(jobs, link, title, 'G', myCat, myPP, myScript,
                                    act, star, order, priority=defPriority)
                        if act:
                            new_downloads.append(title)
                    else:
                        _HandleLink(jobs, link, title, 'B', myCat, myPP, myScript,
                                    False, star, order, priority=defPriority)
            order += 1

        # Send email if wanted and not "forced"
        if new_downloads and cfg.email_rss() and not force:
            emailer.rss_mail(feed, new_downloads)

        # If links are in table for more than 4 weeks, remove
        # Flag old D/B links as obsolete, so that they don't show up in Preview
        now = time.time()
        limit =  now - 4*7*24*3600
        olds  = jobs.keys()
        for old in olds:
            if old not in newlinks:
                if jobs[old].get('status', ' ')[0] in ('G', 'B'):
                    jobs[old]['status'] = 'X'
                try:
                    tm = float(jobs[old]['time'])
                except:
                    # Fix missing timestamp in older RSS_DATA.SAB file
                    jobs[old]['time'] = now
                    tm = now
                if tm < limit:
                    logging.debug("Purging link %s", old)
                    del jobs[old]

        return ''

    def run(self):
        """ Run all the URI's and filters """
        # Protect against second scheduler call before current
        # run is completed. Cannot use LOCK, because run_feed
        # already uses the LOCK.

        if not (self.__running or sabnzbd.PAUSED_ALL):
            self.__running = True
            active = False
            feeds = config.get_rss()
            for feed in feeds:
                if feeds[feed].enable():
                    active = True
                    self.run_feed(feed, download=True, ignoreFirst=True)
                    # Wait 30 seconds, else sites may get irritated
                    for x in xrange(30):
                        if self.shutdown:
                            self.__running = False
                            return
                        else:
                            time.sleep(1.0)
            if active:
                self.save()
            self.__running = False


    @synchronized(LOCK)
    def show_result(self, feed):
        if feed in self.jobs:
            try:
                return self.jobs[feed]
            except:
                return {}
        else:
            return {}

    @synchronized(LOCK)
    def save(self):
        sabnzbd.save_admin(self.jobs, sabnzbd.RSS_FILE_NAME)

    @synchronized(LOCK)
    def delete(self, feed):
        if feed in self.jobs:
            del self.jobs[feed]

    @synchronized(LOCK)
    def flag_downloaded(self, feed, id):
        if feed in self.jobs:
            lst = self.jobs[feed]
            for link in lst:
                if lst[link].get('url', '') == id:
                    lst[link]['status'] = 'D'

    @synchronized(LOCK)
    def clear_feed(self, feed):
        # Remove any previous references to this feed name, and start fresh
        if feed in self.jobs:
            del self.jobs[feed]


RE_NEWZBIN = re.compile(r'(newz)(bin|xxx).com/browse/post/(\d+)', re.I)

def _HandleLink(jobs, link, title, flag, cat, pp, script, download, star, order, priority=NORMAL_PRIORITY):
    """ Process one link """
    if script=='': script = None
    if pp=='': pp = None

    jobs[link] = {}
    jobs[link]['order'] = order
    if special_rss_site(link):
        nzbname = None
    else:
        nzbname = sanitize_foldername(title)
    m = RE_NEWZBIN.search(link)
    if m and m.group(1).lower() == 'newz' and m.group(2) and m.group(3):
        if download:
            jobs[link]['status'] = 'D'
            jobs[link]['title'] = title
            logging.info("Adding %s (%s) to queue", m.group(3), title)
            sabnzbd.add_msgid(m.group(3), pp=pp, script=script, cat=cat, priority=priority, nzbname=nzbname)
        else:
            if star:
                jobs[link]['status'] = flag + '*'
            else:
                jobs[link]['status'] = flag
            jobs[link]['title'] = title
            jobs[link]['url'] = m.group(3)
            jobs[link]['cat'] = cat
            jobs[link]['pp'] = pp
            jobs[link]['script'] = script
            jobs[link]['prio'] = str(priority)
    else:
        if download:
            jobs[link]['status'] = 'D'
            jobs[link]['title'] = title
            logging.info("Adding %s (%s) to queue", link, title)
            sabnzbd.add_url(link, pp=pp, script=script, cat=cat, priority=priority, nzbname=nzbname)
        else:
            if star:
                jobs[link]['status'] = flag + '*'
            else:
                jobs[link]['status'] = flag
            jobs[link]['title'] = title
            jobs[link]['url'] = link
            jobs[link]['cat'] = cat
            jobs[link]['pp'] = pp
            jobs[link]['script'] = script
            jobs[link]['prio'] = str(priority)

    jobs[link]['time'] = time.time()


def _get_link(uri, entry):
    """ Retrieve the post link from this entry
        Returns (link, category)
    """
    link = None
    category = ''
    uri = uri.lower()
    if 'newzbin.com' in uri or 'newzxxx.com'in uri:
        link = entry.link
        if not (link and '/post/' in link.lower()):
            # Use alternative link
            link = entry.links[0].href
    elif 'nzbindex.nl' in uri or 'nzbindex.com' in uri or 'animeusenet.org' in uri:
        link = entry.enclosures[0]['href']
    elif 'feed.nzbclub.com' in uri:
        link = entry.link
        if link:
            link = link.replace('nzb_view.aspx', 'nzb_download.aspx')
    elif not link:
        # Try standard link first
        link = entry.link
        if not link:
            link = entry.links[0].href

    if link and 'http' in link.lower():
        try:
            category = entry.cattext
        except:
            try:
                category = entry.category
            except:
                category = ''
        return link, category
    else:
        logging.warning(Ta('warn-emptyRSS@1'), link)
        return None, ''


def special_rss_site(url):
    """ Return True if url describes an RSS site with odd titles
    """
    return 'nzbindex.nl/' in url or 'nzbindex.com/' in url or 'nzbclub.com/' in url
