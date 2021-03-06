"""
 Copyright (c) 2012-2015 Kuan-Chung Chiu <buganini@gmail.com>

 Redistribution and use in source and binary forms, with or without
 modification, are permitted provided that the following conditions
 are met:
 1. Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
 2. Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.

 THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS ``AS IS'' AND
 ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 ARE DISCLAIMED.  IN NO EVENT SHALL THE REGENTS OR CONTRIBUTORS BE LIABLE
 FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
 OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
 OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
 SUCH DAMAGE.
"""

from PyQt5 import QtCore, QtGui
import os
import math
from PIL import Image
import subprocess
import weakref
import xml.dom.minidom

import cluto
from helpers import *
from item import Item
import imglib

cache_pil_rgb = {}
cache_pil_l = {}

class ImageItem(Item):
    @staticmethod
    def probe(filename):
        return os.path.splitext(filename.lower())[1] in (".jpg", ".png", ".jpeg", ".tiff", ".bmp")

    @staticmethod
    def addItem(core, path):
        item = ImageItem(path = path, x1 = 0, y1 = 0, x2 = -1, y2 = -1)
        core.clips.append(item)

    def __init__(self, **args):
        super(ImageItem, self).__init__(**args)
        if self.x2==-1 or self.y2==-1:
            im = Image.open(self.getFullPath())
            self.x2, self.y2 = im.size
            del(im)

    def get_pil_rgb(self):
        global cache_pil_rgb
        oid = id(self.path)
        try:
            o = cache_pil_rgb[oid]()
        except:
            o = None
        if not o:
            o = Image.open(self.getFullPath()).convert('RGB')
            cache_pil_rgb[oid] = weakref.ref(o)
        return o

    def get_pil_l(self):
        global cache_pil_l
        oid = id(self.path)
        try:
            o = cache_pil_l[oid]()
        except:
            o = None
        if not o:
            o = Image.open(self.getFullPath()).convert('L')
            cache_pil_l[oid] = weakref.ref(o)
        return o

    def get_pil_cropped(self):
        return Image.open(self.getFullPath()).convert('RGB').crop((self.x1, self.y1, self.x2, self.y2))

    def get_cropped(self):
        bfile = os.path.join(self.getWorkdir(), "cropped-%dx%dx%dx%d.jpg" % (self.x1, self.y1, self.x2, self.y2))
        if not os.path.exists(bfile):
            im = self.get_pil_rgb().crop((self.x1, self.y1, self.x2, self.y2))
            im.save(bfile)
            del(im)
        return bfile

    def getContent(self):
        return self.get_pil_cropped()

    def __call__(self):
        self.get_cropped()
        cluto.instance.worker.addBgJobs(self.children)

    def drawQT(self, painter, xoff, yoff, scale=1):
        pixmap = QtGui.QPixmap(self.get_cropped())
        w, h = self.getSize()
        painter.scale(scale, scale)
        painter.drawPixmap(xoff, yoff, w, h, pixmap)

    def check_boundary(self, x1, y1, x2, y2):
        im = self.get_pil_l()
        return imglib.boundary_check(im, x1, y1, x2, y2)

    def ocr(self):
        if 'text' in self.tags:
            return
        tempdir = os.path.join(self.getWorkdir(), "ocr")
        if not os.path.exists(tempdir):
            os.makedirs(tempdir)
        im = self.get_pil_cropped()
        tmpfile = os.path.join(tempdir, "clip.bmp")
        im.save(tmpfile)
        del(im)
        os.chdir(tempdir)

        text = self.tesseract_ocr(tmpfile)

        self.tags['ocr_raw'] = text
        text = cluto.instance.evalRegex(text)
        self.tags['text'] = text
        cluto.instance.addTag('ocr_raw')
        cluto.instance.addTag('text')

    def trim(self, left, top, right, bottom, margin=0):
        x1 = self.x1
        y1 = self.y1
        x2 = self.x2
        y2 = self.y2
        im = self.get_pil_l()

        if left:
            x1 = imglib.leftTrim(im, x1, y1, x2, y2, margin)
        if top:
            y1 = imglib.topTrim(im, x1, y1, x2, y2, margin)
        if right:
            x2 = imglib.rightTrim(im, x1, y1, x2, y2, margin)
        if bottom:
            y2 = imglib.bottomTrim(im, x1, y1, x2, y2, margin)

        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

        cluto.instance.worker.addBgJob(self)

    def _getLines(self):
        return imglib.getLines(self.getFullPath(), self.x1, self.y1, self.x2, self.y2)