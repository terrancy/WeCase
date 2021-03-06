#!/usr/bin/env python3
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

# WeCase -- This model implemented Model and Item for tweets
# Copyright: GPL v3 or later.


from PyQt4 import QtCore
from datetime import datetime
from http.client import BadStatusLine
from urllib.error import URLError
from TweetUtils import get_mid
from WTimeParser import WTimeParser as time_parser
from WeHack import async, UNUSED
from TweetUtils import tweetLength
import const
import logging


class TweetSimpleModel(QtCore.QAbstractListModel):
    rowInserted = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super(TweetSimpleModel, self).__init__(parent)
        self._tweets = []
        self._tweetKeywordBlacklist = []
        self._usersBlackList = []

    def appendRow(self, item):
        self.insertRow(self.rowCount(), item)

    def appendRows(self, items):
        for item in items:
            self.appendRow(TweetItem(item))

    def clear(self):
        self._tweets = []

    def data(self, index, role):
        return self._tweets[index.row()].data(role)

    def get_item(self, row):
        return self._tweets[row]

    def insertRow(self, row, item):
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._tweets.insert(row, item)
        self.rowInserted.emit(row)
        self.endInsertRows()

    def insertRows(self, row, items):
        self.beginInsertRows(QtCore.QModelIndex(), row, row + len(items) - 1)
        for item in items:
            self._tweets.insert(row, TweetItem(item))
            self.rowInserted.emit(row)
        self.endInsertRows()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._tweets)


class TweetTimelineBaseModel(TweetSimpleModel):

    timelineLoaded = QtCore.pyqtSignal()
    nothingLoaded = QtCore.pyqtSignal()

    def __init__(self, timeline=None, parent=None):
        super(TweetTimelineBaseModel, self).__init__(parent)
        self.timeline = timeline
        self.lock = False

    def timeline_get(self):
        raise NotImplementedError

    def timeline_new(self):
        raise NotImplementedError

    def timeline_old(self):
        raise NotImplementedError

    def first_id(self):
        assert self._tweets
        return int(self._tweets[0].id)

    def last_id(self):
        assert self._tweets
        return int(self._tweets[-1].id)

    def _load_next_page(self):
        self.page += 1
        timeline = lambda: self.timeline_get(page=self.page)
        return timeline

    def setTweetsKeywordsBlacklist(self, blacklist):
        self._tweetKeywordBlacklist = blacklist

    def setUsersBlacklist(self, blacklist):
        self._usersBlackList = blacklist

    def _inBlacklist(self, tweet):
        if not tweet:
            return False
        elif self._inBlacklist(tweet.original):
            return True

        # Put all your statements at here
        if tweet.withKeywords(self._tweetKeywordBlacklist):
            return True
        if tweet.author and (tweet.author.name in self._usersBlackList):
            return True
        return False

    def filter(self, items):
        new_items = []
        for item in items:
            if self._inBlacklist(TweetItem(item)):
                continue
            else:
                new_items.append(item)
        return new_items

    @async
    def _common_get(self, timeline_func, pos):
        def tprint(*args):
            import threading
            logging.debug(threading.current_thread().name + " " + "".join(*args))

        if self.lock:
            return
        self.lock = True

        while 1:
            # try until success
            try:
                # timeline is just a pointer to the method.
                # We are in another thread now, call it. UI won't freeze.
                timeline = timeline_func()
                break
            except (BadStatusLine, URLError, OSError):
                # OSError: CRC Check Failed...
                tprint("Retrying...")
                continue

        # Timeline is not blank, but after filter(), timeline is blank.
        while timeline and (not self.filter(timeline)):
            # All tweets in this page are removed.
            # Load next page.
            if timeline_func == self.timeline_new:
                # We are fetching new tweet, do nothing.
                break

            # We are not fetch new tweets.
            timeline = self._load_next_page()()

        timeline = self.filter(timeline)
        if not timeline:
            self.nothingLoaded.emit()

        if pos == -1:
            self.appendRows(timeline)
        else:
            self.insertRows(pos, timeline)
        self.lock = False

    def load(self):
        self.page = 1
        timeline = self.timeline_get
        self._common_get(timeline, -1)

    def new(self):
        timeline = self.timeline_new
        self._common_get(timeline, 0)
        self.timelineLoaded.emit()

    def next(self):
        timeline = self.timeline_old
        self._common_get(timeline, -1)


class TweetCommonModel(TweetTimelineBaseModel):

    def __init__(self, timeline=None, parent=None):
        super(TweetCommonModel, self).__init__(timeline, parent)

    def timeline_get(self, page=1):
        timeline = self.timeline.get(page=page).statuses
        return timeline

    def timeline_new(self):
        timeline = self.timeline.get(since_id=self.first_id()).statuses[::-1]
        return timeline

    def timeline_old(self):
        timeline = self.timeline.get(max_id=self.last_id()).statuses
        timeline = timeline[1::]
        return timeline


class TweetUserModel(TweetTimelineBaseModel):

    def __init__(self, timeline, uid, parent=None):
        super(TweetUserModel, self).__init__(timeline, parent)
        self._uid = uid

    def timeline_get(self, page=1):
        timeline = self.timeline.get(page=page, uid=self._uid).statuses
        return timeline

    def timeline_new(self):
        timeline = self.timeline.get(since_id=self.first_id(),
                                     uid=self._uid).statuses[::-1]
        return timeline

    def timeline_old(self):
        timeline = self.timeline.get(max_id=self.last_id(), uid=self._uid).statuses
        timeline = timeline[1::]
        return timeline

    def uid(self):
        return self._uid


class TweetCommentModel(TweetTimelineBaseModel):

    def __init__(self, timeline=None, parent=None):
        super(TweetCommentModel, self).__init__(timeline, parent)
        self.page = 0

    def timeline_get(self, page=1):
        timeline = self.timeline.get(page=page).comments
        return timeline

    def timeline_new(self):
        timeline = self.timeline.get(since_id=self.first_id()).comments[::-1]
        return timeline

    def timeline_old(self):
        timeline = self.timeline.get(max_id=self.last_id()).comments
        timeline = timeline[1::]
        return timeline


class TweetUnderCommentModel(TweetTimelineBaseModel):
    def __init__(self, timeline=None, id=0, parent=None):
        super(TweetUnderCommentModel, self).__init__(timeline, parent)
        self.id = id

    def timeline_get(self, page=1):
        timeline = self.timeline.get(id=self.id, page=page).comments
        return timeline

    def timeline_new(self):
        timeline = self.timeline.get(id=self.id, since_id=self.first_id()).comments[::-1]
        return timeline

    def timeline_old(self):
        timeline = self.timeline.get(id=self.id, max_id=self.last_id()).comments
        timeline = timeline[1::]
        return timeline


class TweetRetweetModel(TweetTimelineBaseModel):
    def __init__(self, timeline=None, id=0, parent=None):
        super(TweetRetweetModel, self).__init__(timeline, parent)
        self.id = id

    def timeline_get(self, page=1):
        timeline = self.timeline.get(id=self.id, page=page).reposts
        return timeline

    def timeline_new(self):
        timeline = self.timeline.get(id=self.id, since_id=self.first_id()).reposts[::-1]
        return timeline

    def timeline_old(self):
        timeline = self.timeline.get(id=self.id, max_id=self.last_id()).reposts
        timeline = timeline[1::]
        return timeline


class TweetTopicModel(TweetTimelineBaseModel):

    def __init__(self, timeline, topic, parent=None):
        super(TweetTopicModel, self).__init__(timeline, parent)
        self._topic = topic.replace("#", "")
        self.page = 1

    def timeline_get(self):
        timeline = self.timeline.get(q=self._topic, page=self.page).statuses
        return timeline

    def timeline_new(self):
        timeline = self.timeline.get(q=self._topic, page=1).statuses[::-1]
        for tweet in timeline:
            if TweetItem(tweet).id == self.first_id():
                return reversed(timeline[:timeline.index(tweet)])
        return timeline

    def timeline_old(self):
        self.page += 1
        return self.timeline_get()

    def topic(self):
        return self._topic


class UserItem(QtCore.QObject):
    def __init__(self, item, parent=None):
        UNUSED(parent)
        # HACK: Ignore parent, can't create a child with different thread.
        # Where is the thread? I don't know...
        super(UserItem, self).__init__()
        self._data = item
        self.client = const.client

        if self._data.get('id') and self._data.get('name'):
            return
        else:
            self._loadCompleteInfo()

    def _loadCompleteInfo(self):
        if self._data.get('id'):
            self._data = self.client.users.show.get(uid=self._data.get('id'))
        elif self._data.get('name'):
            self._data = self.client.users.show.get(screen_name=self._data.get('name'))

    @QtCore.pyqtProperty(int, constant=True)
    def id(self):
        return self._data.get('id')

    @QtCore.pyqtProperty(str, constant=True)
    def name(self):
        return self._data.get('name')

    @QtCore.pyqtProperty(str, constant=True)
    def avatar(self):
        return self._data.get('profile_image_url')

    @QtCore.pyqtProperty(str, constant=True)
    def verify_type(self):
        typ = self._data.get("verified_type")
        if typ == 0:
            return "personal"
        elif typ in [1, 2, 3, 4, 5, 6, 7]:
            return "organization"
        else:
            return None

    @QtCore.pyqtProperty(str, constant=True)
    def verify_reason(self):
        return self._data.get("verified_reason")


class TweetItem(QtCore.QObject):
    TWEET = 0
    RETWEET = 1
    COMMENT = 2

    def __init__(self, data={}, parent=None):
        super(TweetItem, self).__init__(parent)
        self._data = data
        self.client = const.client
        self.__isFavorite = False

    @QtCore.pyqtProperty(int, constant=True)
    def type(self):
        if "retweeted_status" in self._data:
            return self.RETWEET
        elif "status" in self._data:
            return self.COMMENT
        else:
            return self.TWEET

    @QtCore.pyqtProperty(int, constant=True)
    def id(self):
        return self._data.get('id')

    @QtCore.pyqtProperty(str, constant=True)
    def mid(self):
        decimal_mid = str(self._data.get('mid'))
        encode_mid = get_mid(decimal_mid)
        return encode_mid

    @QtCore.pyqtProperty(str, constant=True)
    def url(self):
        try:
            uid = self._data['user']['id']
            mid = get_mid(self._data['mid'])
        except KeyError:
            # Sometimes Sina's API doesn't return user
            # when our tweet is deeply nested. Just forgot it.
            return ""
        return 'http://weibo.com/%s/%s' % (uid, mid)

    @QtCore.pyqtProperty(QtCore.QObject, constant=True)
    def author(self):
        if "user" in self._data:
            self._user = UserItem(self._data.get('user'), self)
            return self._user
        else:
            return None

    @QtCore.pyqtProperty(str, constant=True)
    def time(self):
        if not self.timestamp:
            return

        passedSeconds = self.passedSeconds
        if passedSeconds < 0:
            return self.tr("Future!")
        elif passedSeconds < 60:
            return self.tr("%.0fs ago") % passedSeconds
        elif passedSeconds < 3600:
            return self.tr("%.0fm ago") % (passedSeconds / 60)
        elif passedSeconds < 86400:
            return self.tr("%.0fh ago") % (passedSeconds / 3600)
        else:
            return self.tr("%.0fd ago") % (passedSeconds / 86400)

    @QtCore.pyqtProperty(str, constant=True)
    def timestamp(self):
        return self._data.get('created_at')

    @QtCore.pyqtProperty(str, constant=True)
    def text(self):
        return self._data.get('text')

    @QtCore.pyqtProperty(QtCore.QObject, constant=True)
    def original(self):
        if self.type == self.RETWEET:
            self._original = TweetItem(self._data.get('retweeted_status'))
            return self._original
        elif self.type == self.COMMENT:
            self._original = TweetItem(self._data.get('status'))
            return self._original
        else:
            return None

    @QtCore.pyqtProperty(str, constant=True)
    def thumbnail_pic(self):
        return self._data.get('thumbnail_pic', "")

    @QtCore.pyqtProperty(str, constant=True)
    def original_pic(self):
        return self._data.get('original_pic')

    @QtCore.pyqtProperty(int, constant=True)
    def retweets_count(self):
        return self._data.get('reposts_count', 0)

    @QtCore.pyqtProperty(int, constant=True)
    def comments_count(self):
        return self._data.get('comments_count', 0)

    @QtCore.pyqtProperty(int, constant=True)
    def passedSeconds(self):
        create = time_parser().parse(self.timestamp)
        create_utc = (create - create.utcoffset()).replace(tzinfo=None)
        now_utc = datetime.utcnow()

        # Always compare UTC time, do NOT compare LOCAL time.
        # See http://coolshell.cn/articles/5075.html for more details.
        if now_utc < create_utc:
            # datetime do not support negative numbers
            return -1
        else:
            passedSeconds = (now_utc - create_utc).total_seconds()
            return passedSeconds

    def isFavorite(self):
        return self.__isFavorite

    def _cut_off(self, text):
        cut_text = ""
        for char in text:
            if tweetLength(cut_text) >= 140:
                break
            else:
                cut_text += char
        return cut_text

    def append_existing_replies(self, text=""):
        if self.original.original:
            text += "//@%s:%s//@%s:%s" % (
                    self.author.name, self.text,
                    self.original.author.name, self.original.text)
        else:
            text += "//@%s:%s" % (self.author.name, self.text)
        return text

    def reply(self, text, comment_ori=False, retweet=False):
        self.client.comments.reply.post(id=self.original.id, cid=self.id,
                                        comment=text, comment_ori=int(comment_ori))
        if retweet:
            text = self.append_existing_replies(text)
            text = self._cut_off(text)
            self.original.retweet(text)

    def retweet(self, text, comment=False, comment_ori=False):
        self.client.statuses.repost.post(id=self.id, status=text,
                                         is_comment=int(comment + comment_ori * 2))

    def comment(self, text, comment_ori=False, retweet=False):
        self.client.comments.create.post(id=self.id, comment=text,
                                         comment_ori=int(comment_ori))
        if retweet:
            self.retweet(text)

    def delete(self):
        if self.type in [self.TWEET, self.RETWEET]:
            self.client.statuses.destroy.post(id=self.id)
        elif self.type == self.COMMENT:
            self.client.comments.destroy.post(cid=self.id)

    def setFavorite(self, state):
        if self.type not in [self.TWEET, self.RETWEET]:
            raise TypeError

        if state:
            assert(not self.__isFavorite)
            self.client.favorites.create.post(id=self.id)
            self.__isFavorite = True
        else:
            assert(self.__isFavorite)
            self.client.favorites.destroy.post(id=self.id)
            self.__isFavorite = False

    def setFavoriteForce(self, state):
        self.__isFavorite = bool(state)

    def refresh(self):
        if self.type in [self.TWEET, self.RETWEET]:
            self._data = self.client.statuses.show.get(id=self.id)

    def withKeyword(self, keyword):
        if keyword in self.text:
            return True
        else:
            return False

    def withKeywords(self, keywords):
        for keyword in keywords:
            if self.withKeyword(keyword):
                return True
        return False
