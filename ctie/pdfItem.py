"""
 Copyright (c) 2015 Kuan-Chung Chiu <buganini@gmail.com>

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

from __future__ import division
from gi.repository import Gtk, Gdk, Poppler
import cairo
import pdf

from item import Item

cache_pdf = {}
cache_pdf_page = {}
lastRender = None

class PdfItem(Item):
	@staticmethod
	def probe(filename):
		return filename.lower().endswith(".pdf")

	def __init__(self, pdf=None, page=None, **args):
		global cache_pdf
		super(PdfItem, self).__init__(**args)
		self.page = page
		if self.page is None:
			self.page = self.parent.page
		if pdf:
			cache_pdf[self.path] = pdf
		if self.x2==-1 or self.y2==-1:
			self.x2, self.y2 = self.getPdfPage().get_size()
		self.text = None
		self.image = None
		self.table = None
		self.rowSep = []
		self.colSep = []


	def addRowSep(self, pos):
		self.rowSep.append(pos)
		self.rowSep.sort()

	def addColSep(self, pos):
		self.colSep.append(pos)
		self.colSep.sort()

	def getTypes(self):
		return ("Text", "Image", "Table")

	def getType(self):
		if self.parent:
			default = self.parent.getType()
		else:
			default = "Text"
		return self.tags.get("_type", default)

	def getExtension(self):
		if self.getType()=="Text":
			return "txt"
		elif self.getType()=="Image":
			if self.image is None:
				self.image = pdf.getImage(self.path, self.page, self.x1*100, self.y1*100, self.x2*100, self.y2*100)
			return self.image.extension
		elif self.getType()=="Table":
			return "csv"
		else:
			return ""

	def getContent(self):
		if self.getType()=="Text":
			if self.text is None:
				self.text = pdf.getText(self.path, self.page, self.x1*100, self.y1*100, self.x2*100, self.y2*100)
			return self.text
		elif self.getType()=="Image":
			if self.image is None:
				self.image = pdf.getImage(self.path, self.page, self.x1*100, self.y1*100, self.x2*100, self.y2*100)
			return self.image
		elif self.getType()=="Table":
			# if self.table is None:
			self.table = pdf.getTable(self.path, self.page, self.x1*100, self.y1*100, self.x2*100, self.y2*100, rSep=[x*100 for x in self.rowSep], cSep=[x*100 for x in self.colSep])
			return self.table
		else:
			return None

	def drawThumbnail(self, widget, cr):
		cw = widget.get_allocated_width()
		ch = widget.get_allocated_height()
		sw, sh, factor = self.getThumbnailSize(cw, ch)
		pw, ph =self.getPdfPage().get_size()
		pw = int(pw*factor)
		ph = int(ph*factor)
		surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, pw, ph)
		ctx = cairo.Context(surface)
		ctx.scale(factor, factor)
		self.getPdfPage().render(ctx)
		ctx.scale(1/factor, 1/factor)
		pb = Gdk.pixbuf_get_from_surface(ctx.get_target(), 0, 0, pw, ph)
		xo, yo = (cw-sw)/2, (ch-sh)/2
		cr.set_source_rgba(255,255,255,255)
		cr.rectangle(xo, yo, sw, sh)
		cr.fill()
		cr.rectangle(xo, yo, sw, sh)
		Gdk.cairo_set_source_pixbuf(cr, pb, xo-self.x1*factor, yo-self.y1*factor)
		cr.fill()

	def draw(self, widget, cr, factor):
		global lastRender
		cr.set_source_rgba(255,255,255,255)
		cr.paint()
		pw, ph =self.getPdfPage().get_size()
		pw = int(pw*factor)
		ph = int(ph*factor)
		if lastRender and (id(self), factor) == (lastRender[0], lastRender[1]):
			pb = lastRender[2]
		else:
			surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, pw, ph)
			ctx = cairo.Context(surface)
			ctx.scale(factor, factor)
			self.getPdfPage().render(ctx)
			ctx.scale(1/factor, 1/factor)
			pb = Gdk.pixbuf_get_from_surface(ctx.get_target(), 0, 0, pw, ph)
			lastRender = (id(self), factor, pb)
		Gdk.cairo_set_source_pixbuf(cr, pb, -self.x1*factor, -self.y1*factor)
		cr.paint()

	def getPdfPage(self):
		global cache_pdf, cache_pdf_page
		if self.path not in cache_pdf:
			cache_pdf[self.path] = Poppler.Document.new_from_file("file://"+self.path, None)
		if self.path not in cache_pdf_page:
			cache_pdf_page[self.path]={}
		if self.page not in cache_pdf_page[self.path]:
			cache_pdf_page[self.path][self.page] = cache_pdf[self.path].get_page(self.page)
		return cache_pdf_page[self.path][self.page]
