#!/usr/bin/env python3
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

# WeCase -- This model implemented a model for smileies.
# Copyright: GPL v3 or later.


import sys
import os
import const
from WeHack import Singleton
from collections import OrderedDict
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
from PyQt4 import QtCore

myself_name = sys.argv[0].split('/')[-1]
myself_path = os.path.abspath(sys.argv[0]).replace(myself_name, "")


class FaceItem():
    def __init__(self, xml_node):
        super(FaceItem, self).__init__()
        self.__xml_node = xml_node

    @property
    def name(self):
        return self.__xml_node.get("tip")

    @property
    def path(self):
        return const.face_path + self.__xml_node[0].text

    @property
    def category(self):
        return self.__xml_node[0].text.split("/")[0]


class FaceModel(metaclass=Singleton):
    nameRole = QtCore.Qt.UserRole + 1
    pathRole = QtCore.Qt.UserRole + 2

    def __init__(self):
        super(FaceModel, self).__init__()
        self.faces = []
        self.__loaded = False

    def appendRow(self, item):
        self.insertRow(self.rowCount(), item)

    def insertRow(self, row, item):
        self.faces.insert(row, item)

    def items(self):
        faces = OrderedDict()

        category = ""
        for face in self.faces:
            if category != face.category:
                category = face.category
                faces[category] = []
            else:
                faces[category].append(face)

        return faces

    def dic(self):
        dic = {}
        for face in self.faces:
            dic[face.name] = face.path
        return dic

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self.faces)

    def gridSize(self):
        size = self.__tree.find("./WNDCONFIG/Align")
        width = int(size.get("Col"))
        height = int(size.get("Row"))
        return QtCore.QSize(width, height)

    def init(self):
        if self.__loaded:
            return

        self.__tree = ET.ElementTree(file=const.face_path + "./face.xml")

        for face in self.__tree.iterfind("./FACEINFO/"):
            assert face.tag == "FACE"
            self.appendRow(FaceItem(face))
        self.__loaded = True
