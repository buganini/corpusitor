"""
 Copyright (c) 2012-2014 Kuan-Chung Chiu <buganini@gmail.com>

 Permission to use, copy, modify, and distribute this software for any
 purpose with or without fee is hereby granted, provided that the above
 copyright notice and this permission notice appear in all copies.

 THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 WHATSOEVER RESULTING FROM LOSS OF MIND, USE, DATA OR PROFITS, WHETHER
 IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING
 OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

"""

import os
import sys
import glob
from gi.repository import Gtk, Gdk, cairo, GObject, Pango
import md5
import Image
import re
import weakref
import pickle
import subprocess
import uuid
import math
from pyquery import PyQuery as pq
from helpers import *
from cql import *
import imglib

os.putenv("TESSDATA_PREFIX", "/usr/share")

threshold=30

id_map={}
cache_gtk={}
cache_pixbuf={}
cache_pil_rgb={}
cache_pil_l={}
clear_tempdir=True

def click(o):
	evt=Gdk.Event(Gdk.EventType.BUTTON_PRESS)
	evt.button.type=Gdk.EventType.BUTTON_PRESS
	evt.button.button=1
	o.emit("button-press-event", evt)

class Item(object):
	def __init__(self, p):
		self.p=p
		self.hash=id_map[p['path']]

	def get_gtk(self):
		global cache_gtk
		oid=id(self.p)
		try:
			o=cache_gtk[oid]()
#			o=cache_gtk[oid]
		except:
			o=None
		if not o:
			o=Gtk.Image.new_from_file(self.get_cropped())
			cache_gtk[oid]=weakref.ref(o)
#			cache_gtk[oid]=o
		return o

	def get_pixbuf(self):
		global cache_pixbuf
		oid=id(self.p)
		try:
			o=cache_pixbuf[oid]()
		except:
			o=None
		if not o:
			o=self.get_gtk().get_pixbuf()
			cache_pixbuf[oid]=weakref.ref(o)
		return o

	def get_pil_rgb(self):
		global cache_pil_rgb
		oid=id(self.p['path'])
		try:
			o=cache_pil_rgb[oid]()
		except:
			o=None
		if not o:
			o=Image.open(self.p['path']).convert('RGB')
			cache_pil_rgb[oid]=weakref.ref(o)
		return o

	def get_pil_l(self):
		global cache_pil_l
		oid=id(self.p['path'])
		try:
			o=cache_pil_l[oid]()
		except:
			o=None
		if not o:
			o=Image.open(self.p['path']).convert('L')
			cache_pil_l[oid]=weakref.ref(o)
		return o

	def get_pil_cropped(self):
		return Image.open(self.p['path']).convert('RGB').crop((self.p['x1'], self.p['y1'], self.p['x2'], self.p['y2']))

	def get_cropped(self):
		bfile=os.path.join(get_tempdir(), "%s-%dx%dx%dx%d.jpg" % (self.hash, self.p['x1'], self.p['y1'], self.p['x2'], self.p['y2']))
		if not os.path.exists(bfile):
			im=self.get_pil_rgb().crop((self.p['x1'], self.p['y1'], self.p['x2'], self.p['y2']))
			im.save(bfile)
			del(im)
		return bfile

	def get_thumbnail(self):
		tfile=os.path.join(get_tempdir(), "%s-%dx%dx%dx%d-thumbnail.jpg" % (self.hash, self.p['x1'], self.p['y1'], self.p['x2'], self.p['y2']))
		if not os.path.exists(tfile):
			im=Image.open(self.get_cropped())
			ow,oh=im.size
			nw,nh=(160,240)
			if float(ow)/oh>float(nw)/nh:
				newsize=(nw, int(math.ceil(float(nw)*oh/ow)))
			else:
				newsize=(int(math.ceil(float(nh)*ow/oh)), nh)
			if newsize[0]<im.size[0] and newsize[1]<im.size[1]:
				im.thumbnail(newsize)
			else:
				im=im.resize(newsize)
			im.save(tfile)
			del(im)
		return tfile

	def get_ocr_tempdir(self):
		rpath="%s-%dx%dx%dx%d" % (self.hash, self.p['x1'], self.p['y1'], self.p['x2'], self.p['y2'])
		os.chdir(get_tempdir())
		return rpath

class CTIE(object):
	def __init__(self):
		self.regex=[]
		self.signal_mask=False
		self.items_filter=None
		self.focus_field=(None, None)
		self.focus_entry=None
		self.clipboard=[]
		self.selections=[]
		self.curr_level=None
		self.last_level=None
		self.focus_item=None
		self.last_focus=None
		self.canvas=None
		self.clips=[]
		self.zoom=100
		self.selstart=(None, None)
		self.selend=(None, None)
		self.tags=[]
		self.copy_tag=[]
		self.mode=None
		self.builder = Gtk.Builder()
		for datadir in ['.','/usr/local/share/ctie']:
			fullpath=os.path.join(datadir, 'ctie.xml')
			if os.path.exists(fullpath):
				break
		else:
			sys.stderr.write('Unable to find ctie.xml\n')
			sys.exit(1)

		self.builder.add_from_file(fullpath)
		self.window = self.builder.get_object("main_window")
		self.window.connect("delete-event", Gtk.main_quit)

		level=self.builder.get_object("level")
		level.set_entry_text_column(0)
		level.connect("changed", self.change_level)
		self.level_sanitize()

		#css
		self.css=Gtk.CssProvider()
		self.css.load_from_path(os.path.join(datadir, 'ctie.css'))

		#keyboard shortcut
		self.window.connect("key-press-event", self.key_press)

		#menubar
		menu_batch=self.builder.get_object('menu_batch')

		item=Gtk.MenuItem.new_with_label("Trim Left-Top")
		item.connect("activate", self.ltrim)
		menu_batch.attach(item, 0, 1, 0, 1)

		item=Gtk.MenuItem.new_with_label("Trim Right-Bottom")
		item.connect("activate", self.rtrim)
		menu_batch.attach(item, 0, 1, 1, 2)

		item=Gtk.MenuItem.new_with_label("Set Value")
		item.connect("activate", self.set_value)
		menu_batch.attach(item, 0, 1, 2, 3)

		menu_batch.show_all()

		#toolbar
		toolbar=self.builder.get_object('toolbar')

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_OPEN, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Open Project")
		button.set_image(btn_img)
		button.connect("clicked", self.open_project)
		toolbar.pack_start(button, False, False, 0)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_SAVE, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Save Project")
		button.set_image(btn_img)
		button.connect("clicked", self.save_project)
		toolbar.pack_start(button, False, False, 0)

		toolbar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 1)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_ADD, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Add Item")
		button.set_image(btn_img)
		button.connect("clicked", self.add_item)
		toolbar.pack_start(button, False, False, 0)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_REMOVE, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Remove Item")
		button.set_image(btn_img)
		button.connect("clicked", self.remove_item)
		toolbar.pack_start(button, False, False, 0)

		toolbar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 1)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_ZOOM_IN, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Zoom In")
		button.set_image(btn_img)
		button.connect("clicked", self.zoom_in)
		button.set_property("focus-on-click", True)
		toolbar.pack_start(button, False, False, 0)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_ZOOM_OUT, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Zoom Out")
		button.set_image(btn_img)
		button.connect("clicked", self.zoom_out)
		button.set_property("focus-on-click", True)
		toolbar.pack_start(button, False, False, 0)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_ZOOM_100, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Zoom 100%")
		button.set_image(btn_img)
		button.connect("clicked", self.zoom_100)
		button.set_property("focus-on-click", True)
		toolbar.pack_start(button, False, False, 0)

		self.btn_zoom_fit=button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_ZOOM_FIT, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Zoom Fit")
		button.set_image(btn_img)
		button.connect("clicked", self.zoom_fit)
		button.set_property("focus-on-click", True)
		toolbar.pack_start(button, False, False, 0)

		toolbar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 1)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_CONVERT, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Regex")
		button.set_image(btn_img)
		button.connect("clicked", lambda x: self.builder.get_object("regex_window").show())
		self.builder.get_object("btn_regex_apply").connect("clicked", self.regex_apply)
		toolbar.pack_start(button, False, False, 0)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_COPY, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Copy")
		button.set_image(btn_img)
		button.connect("clicked", self.copy)
		toolbar.pack_start(button, False, False, 0)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_PROPERTIES, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Copy Settings")
		button.set_image(btn_img)
		button.connect("clicked", self.copy_setting)
		toolbar.pack_start(button, False, False, 0)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_PASTE, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Paste")
		button.set_image(btn_img)
		button.connect("clicked", self.paste)
		button.set_property("focus-on-click", True)
		toolbar.pack_start(button, False, False, 0)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_INFO, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Auto Paste")
		button.set_image(btn_img)
		button.connect("clicked", self.autopaste)
		toolbar.pack_start(button, False, False, 0)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_DELETE, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Delete Selection Area(s)")
		button.set_image(btn_img)
		button.connect("clicked", self.delete)
		toolbar.pack_start(button, False, False, 0)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_REFRESH, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Reset Children Order")
		button.set_image(btn_img)
		button.connect("clicked", self.set_children_order)
		toolbar.pack_start(button, False, False, 0)

		toolbar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 1)

		button=Gtk.Button()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_JUMP_TO, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Export")
		button.set_image(btn_img)
		button.connect("clicked", self.export_show)
		toolbar.pack_start(button, False, False, 0)

		self.toggle_collation=button=Gtk.ToggleButton()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_FIND_AND_REPLACE, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Collation Mode")
		button.set_image(btn_img)
		button.connect("toggled", self.child_tags_refresh)
		toolbar.pack_end(button, False, False, 0)

		self.toggle_ocr=button=Gtk.ToggleButton()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_SELECT_FONT, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("OCR on selecting empty item")
		button.set_image(btn_img)
		button.connect("toggled", lambda x: click(self.focus_item))
		toolbar.pack_end(button, False, False, 0)

		self.toggle_childrenpath=button=Gtk.ToggleButton()
		btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_INFO, Gtk.IconSize.SMALL_TOOLBAR)
		button.set_tooltip_text("Display areas path")
		button.set_image(btn_img)
		button.connect("toggled", lambda x: self.canvas.queue_draw())
		toolbar.pack_end(button, False, False, 0)

		toolbar.show_all()

		#batch
		self.builder.get_object('btn_set_value_close').connect('clicked', lambda x: self.builder.get_object('set_value_window').hide())
		self.builder.get_object('btn_set_value_apply').connect('clicked', self.set_value_apply)

		#items list
		self.builder.get_object("btn_items_filter_apply").connect("clicked", self.items_filter_apply)

		#workarea
		workarea=self.builder.get_object("workarea")
		workarea.connect("scroll-event", self.workarea_mouse)
		workarea.connect("button-press-event", self.workarea_mouse)
		workarea.connect("button-release-event", self.workarea_mouse)
		workarea.connect("motion-notify-event", self.workarea_mouse)

		#collation editor
		collation_editor=self.builder.get_object('collation_editor')
		collation_editor.connect("changed", self.collation_editor_changed)
		collation_editor.modify_font(Pango.FontDescription("Monospace 12"))

		#tag
		self.builder.get_object('auto_fill').set_active(0)
		self.builder.get_object('btn_add_tag').connect('clicked', self.add_tag)

		#export
		self.builder.get_object('btn_export_close').connect('clicked', lambda x: self.builder.get_object('export_window').hide())
		self.builder.get_object('btn_export').connect('clicked', self.do_export)

		#copy setting
		self.builder.get_object('btn_copy_setting_close').connect('clicked', lambda x: self.builder.get_object('copy_setting_window').hide())

		#launch
		self.window.show()

	def set_status(self, s):
		status=self.builder.get_object('statusbar')
		status.remove_all(0)
		status.push(0, s)

	def regex_apply(self, *arg):
		b=self.builder.get_object("regex").get_buffer()
		text=b.get_text(b.get_start_iter(), b.get_end_iter(), 0).strip()
		self.regex=[]
		for line in text.split("\n"):
			try:
				a,b=line.split("\t")
				try:
					self.regex.append((a.decode("UTF-8"), b.decode("utf-8")))
				except:
					pass
			except:
				pass
		self.builder.get_object("regex_window").hide()

	def previous(self, *arg):
		if not self.focus_item:
			return
		focus_p=self.focus_item.p
		if not len(focus_p['children']):
			pass
		elif len(self.selections)!=1:
			self.selections=[0]
		else:
			self.selections[0]-=1
			self.selections[0]+=len(focus_p['children'])
			self.selections[0]%=len(focus_p['children'])
		self.child_tags_refresh()
		self.canvas.queue_draw()
		self.preview_canvas.queue_draw()
		self.set_status('Area: %d Select: %s' % (len(focus_p['children']), ', '.join([str(i+1) for i in self.selections])))

	def next(self, *arg):
		if not self.focus_item:
			return
		focus_p=self.focus_item.p
		if not len(focus_p['children']):
			pass
		elif len(self.selections)!=1:
			self.selections=[0]
		else:
			self.selections[0]+=1
			self.selections[0]%=len(focus_p['children'])
		self.child_tags_refresh()
		self.canvas.queue_draw()
		self.preview_canvas.queue_draw()
		self.set_status('Area: %d Select: %s' % (len(focus_p['children']), ', '.join([str(i+1) for i in self.selections])))

	def key_press(self, obj, evt):
		collation_mode=self.toggle_collation.get_active()
		if evt.keyval==Gdk.KEY_Page_Down:
			if not collation_mode or evt.state & Gdk.ModifierType.CONTROL_MASK:
				next=self.focus_item.next
				if next:
					click(next)
			else:
				self.next()
		elif evt.keyval==Gdk.KEY_Page_Up:
			if not collation_mode or evt.state & Gdk.ModifierType.CONTROL_MASK:
				prev=self.focus_item.prev
				if prev:
					click(prev)
			else:
				self.previous()
		elif evt.keyval==Gdk.KEY_Delete and self.canvas.has_focus():
			self.delete()
		elif (evt.keyval==Gdk.KEY_A or evt.keyval==Gdk.KEY_a) and evt.state & Gdk.ModifierType.CONTROL_MASK and self.canvas.has_focus():
			if not self.focus_item:
				return
			focus_p=self.focus_item.p
			self.selections=[]
			if not evt.state & Gdk.ModifierType.SHIFT_MASK:
				self.selections.extend(range(0, len(focus_p['children'])))
			self.canvas.queue_draw()
		elif (evt.keyval==Gdk.KEY_C or evt.keyval==Gdk.KEY_c) and evt.state & Gdk.ModifierType.CONTROL_MASK and self.canvas.has_focus():
			self.copy()
		elif (evt.keyval==Gdk.KEY_V or evt.keyval==Gdk.KEY_v) and evt.state & Gdk.ModifierType.CONTROL_MASK and self.canvas.has_focus():
			self.paste()

	def ltrim(self, *arg):
		items_list=self.builder.get_object("items_list")
		cs=items_list.get_children()
		todo=[]
		for c in cs:
			p=c.p
			if not p:
				continue
			x1=p['x1']
			y1=p['y1']
			x2=p['x2']
			y2=p['y2']
			it=Item(p)
			im=it.get_pil_l()

			p['x1'] = imglib.leftTrim(im, x1, y1, x2, y2)
			p['y1'] = imglib.topTrim(im, x1, y1, x2, y2)
			todo.extend(p['children'])
		self.edge_limiter(todo)
		self.redraw_items_list()

	def rtrim(self, *arg):
		items_list=self.builder.get_object("items_list")
		cs=items_list.get_children()
		todo=[]
		for c in cs:
			p=c.p
			if not p:
				continue
			x1=p['x1']
			y1=p['y1']
			x2=p['x2']
			y2=p['y2']
			it=Item(p)
			im=it.get_pil_l()

			p['x2'] = imglib.rightTrim(im, x1, y1, x2, y2)
			p['y2'] = imglib.bottomTrim(im, x1, y1, x2, y2)
			todo.extend(p['children'])
		self.edge_limiter(todo)
		self.redraw_items_list()

	def set_value(self, *arg):
		self.builder.get_object('set_value_window').show()

	def set_value_apply(self, *arg):
		key=self.builder.get_object('set_value_key').get_text()
		value=self.builder.get_object('set_value_value').get_text()
		formula=None
		if not key:
			return
		if self.builder.get_object('set_value_value_is_formula').get_active():
			formula=CQL(value)
		if key not in self.tags:
			self.tags.append(key)
		items_list=self.builder.get_object("items_list")
		cs=items_list.get_children()
		todo=[]
		for c in cs:
			p=c.p
			if not p:
				continue
			if formula:
				p["tags"][key]=formula.eval(p)
			else:
				p["tags"][key]=value

	def open_project(self, *arg):
		global id_map, tempdir, clear_tempdir
		filec=Gtk.FileChooserDialog("Open", self.builder.get_object("main_window"), Gtk.FileChooserAction.SAVE, (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.ACCEPT))
		if Gtk.Dialog.run(filec)==Gtk.ResponseType.ACCEPT:
			filename=filec.get_filename()
			fp=open(filename,'r')
			filec.destroy()
			try:
				data=pickle.load(fp)
				fp.close()
				clear_tempdir=False
			except:
				self.set_status('Failed loading %s' % filename)
				return
		else:
			filec.destroy()
			return
		if type(data)==type([]):
			id_map, self.clips, self.tags, self.copy_tag, tempdir=data
			todo=[]
			todo.extend(self.clips)
			while todo:
				newtodo=[]
				for p in todo:
					if 'flags' not in p:
						p['flags']=[]
					newtodo.extend(p['children'])
				todo=newtodo
		else:
			id_map=data['id_map']
			self.clips=data['clips']
			self.tags=data['tags']
			self.copy_tag=data['tags']
			tempdir=data['tempdir']
			self.builder.get_object("regex").get_buffer().set_text(data['regex'])
			self.regex_apply()
		self.level_sanitize()
		self.redraw_items_list()
		self.tags_refresh()

	def save_project(self, *arg):
		global clear_tempdir
		if not self.clips:
			return
		filec=Gtk.FileChooserDialog("Save", self.builder.get_object("main_window"), Gtk.FileChooserAction.SAVE, (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT))
		if Gtk.Dialog.run(filec)==Gtk.ResponseType.ACCEPT:
			b=self.builder.get_object("regex").get_buffer()
			regex=b.get_text(b.get_start_iter(), b.get_end_iter(), 0).strip()
			data={'id_map':id_map, 'clips':self.clips, 'tags':self.tags, 'copy_tags':self.copy_tag, 'tempdir':tempdir, 'regex':regex}
			fp=open(filec.get_filename(),'w')
			pickle.dump(data, fp)
			fp.close()
			clear_tempdir=False
		filec.destroy()

	def copy_setting(self, obj, *arg):
		tagsbox=self.builder.get_object("copy_setting_tags")
		c=tagsbox.get_child()
		if c:
			tagsbox.remove(c)
		tags_table=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		tagsbox.add(tags_table)
		for i,tag in enumerate(self.tags):
			toggle=Gtk.CheckButton.new_with_label(tag)
			if tag in self.copy_tag:
				toggle.set_active(True)
			else:
				toggle.set_active(False)
			toggle.connect('toggled', self.copy_setting_toggle, tag)
			tags_table.pack_start(toggle,False,False,0)
		self.builder.get_object("copy_setting_window").show_all()

	def copy_setting_toggle(self, obj, tag):
		if obj.get_active():
			if tag not in self.copy_tag:
				self.copy_tag.append(tag)
		else:
			if tag in self.copy_tag:
				self.copy_tag.remove(tag)

	def copy(self, *arg):
		if not self.focus_item:
			return
		focus_p=self.focus_item.p
		self.clipboard=[]
		for i in self.selections:
			p=focus_p['children'][i]
			tags={}
			for tag in self.copy_tag:
				if tag in p['tags']:
					tags[tag]=p['tags'][tag]
			self.clipboard.append({'x1':p['x1']-focus_p['x1'], 'y1':p['y1']-focus_p['y1'], 'x2':p['x2']-focus_p['x1'] ,'y2':p['y2']-focus_p['y1'] ,'tags':tags, 'flags':[], 'reference':{}})

	def paste(self, *arg):
		if not self.focus_item:
			return
		focus_p=self.focus_item.p
		self.selections=[]
		cs=[]
		for c in focus_p['children']:
			cs.append((c['x1']-focus_p['x1'], c['y1']-focus_p['y1'], c['x2']-focus_p['x1'], c['y2']-focus_p['y1']))
		for p in self.clipboard:
			tags={}
			for tag in p['tags']:
				tags[tag]=p['tags'][tag]
			x1=p['x1']
			y1=p['y1']
			x2=p['x2']
			y2=p['y2']
			x1=max(x1,0)
			y1=max(y1,0)
			x2=min(x2,focus_p['x2']-focus_p['x1'])
			y2=min(y2,focus_p['y2']-focus_p['y1'])
			if x2-x1>1 and y2-y1>1:
				self.selections.append(len(focus_p['children']))
				if (x1,y1,x2,y2) in cs:
					continue
				focus_p['children'].append({'path':focus_p['path'],'x1':x1+focus_p['x1'],'y1':y1+focus_p['y1'],'x2':x2+focus_p['x1'],'y2':y2+focus_p['y1'],'children':[], 'tags':tags, 'parent':focus_p, 'flags':[], 'reference':{}})
		self.canvas.queue_draw()

	def autopaste(self, *arg):
		if not self.clipboard:
			return
		items_list=self.builder.get_object("items_list")
		cs=items_list.get_children()
		for c in cs:
			p=c.p
			if not p:
				continue
			if len(p['children']):
				continue
			im=Image.open(p['path']).convert('L')
			paste=True
			clipboard=[]
			for cp in self.clipboard:
				x1=cp['x1']
				y1=cp['y1']
				x2=cp['x2']
				y2=cp['y2']
				x1=max(x1,0)
				y1=max(y1,0)
				x2=min(x2,p['x2']-p['x1'])
				y2=min(y2,p['y2']-p['y1'])

				lastpixel=im.getpixel((x1+p['x1'],y1+p['y1']))
				if y1!=0:
					y=y1+p['y1']
					for x in xrange(x1+p['x1']+1,x2+p['x1']-1):
						pixel=im.getpixel((x,y))
						if abs(pixel-lastpixel)>threshold:
							paste=False
							break
						lastpixel=pixel
					if not paste:
						break
				if x2!=p['x2']-p['x1']:
					x=x2+p['x1']-1
					for y in xrange(y1+p['y1']+1,y2+p['y1']-1):
						pixel=im.getpixel((x,y))
						if abs(pixel-lastpixel)>threshold:
							paste=False
							break
						lastpixel=pixel
					if not paste:
						break
				if y2!=p['y2']-p['y1']:
					y=y2+p['y1']-1
					for x in xrange(x1+p['x1']+1,x2+p['x1']):
						pixel=im.getpixel((x,y))
						if abs(pixel-lastpixel)>threshold:
							paste=False
							break
						lastpixel=pixel
					if not paste:
						break
				if x1!=0:
					x=x1+p['x1']
					for y in xrange(y1+p['y1']+1,y2+p['y1']):
						pixel=im.getpixel((x,y))
						if abs(pixel-lastpixel)>threshold:
							paste=False
							break
						lastpixel=pixel
				clipboard.append({'x1':x1,'y1':y1,'x2':x2,'y2':y2,'tags':cp['tags']})
			if not paste:
				continue
			del(im)
			for cp in clipboard:
				tags={}
				for tag in cp['tags']:
					tags[tag]=cp['tags'][tag]
				if x2-x1>1 and y2-y1>1:
					p['children'].append({'path':p['path'],'x1':cp['x1']+p['x1'],'y1':cp['y1']+p['y1'],'x2':cp['x2']+p['x1'],'y2':cp['y2']+p['y1'],'children':[], 'tags':tags, 'parent':p, 'flags':[], 'reference':{}})
		self.canvas.queue_draw()

	def delete(self, *arg):
		if not self.focus_item:
			return
		focus_p=self.focus_item.p
		self.selections.sort()
		self.selections.reverse()
		for i in self.selections:
			del(focus_p['children'][i])
		self.selections=[]
		self.canvas.queue_draw()
		self.child_tags_refresh()

	def do_export(self, *arg):
		s=self.clips
		outputdir=self.builder.get_object('output_dir').get_filename()
		ef=CQL(self.builder.get_object('export_filter').get_text())
		if not ef:
			return
		ec=CQL(self.builder.get_object('export_content').get_text())
		if not ec:
			return
		ep=CQL(self.builder.get_object('path_pattern').get_text())
		if not ep:
			return
		while s:
			ns=[]
			for p in s:
				if ef.eval(p):
					t=p
					tags={}
					while t:
						for tag in t['tags']:
							if tag not in tags:
								tags[tag]=t['tags'][tag]
						t=t['parent']
					for tag in self.tags:
						if tag not in tags:
							tags[tag]=""

					path=ep.eval(p)
					path=os.path.join(outputdir, path)
					pdir=os.path.dirname(path)
					if not os.path.exists(pdir):
						os.makedirs(pdir)
					if os.path.exists(path):
						print "Exists:", path
					cnt=ec.eval(p)
					if str(cnt).startswith("<Image") or str(cnt).startswith("<PIL.Image"):
						cnt.save(path)
					elif type(cnt)==str:
						f=open(path,'w')
						f.write(cnt)
						f.close()
				ns.extend(p['children'])
			s=ns

	def append_tag(self, *arg):
		b=self.builder.get_object('path_pattern')
		b.set_text("%s${%s}" % (b.get_text(), self.builder.get_object('tags_list').get_active_text()))

	def export_show(self, *arg):
		self.builder.get_object('export_window').show()

	def add_tag(self, *arg):
		tag=self.builder.get_object('new_tag').get_text()
		if tag and not tag in self.tags:
			self.tags.append(tag)
		else:
			self.set_status("Tag %s already exists" % tag)
		self.tags_refresh()

	def canvas_draw(self, widget, cr):
		if not self.focus_item:
			return
		p=self.focus_item.p
		factor=self.zoom*0.01
		width=p['x2']-p['x1']
		height=p['y2']-p['y1']

		cr.scale(factor, factor)
		self.canvas.set_size_request(int(width*factor), int(height*factor))
		self.canvas.set_halign(Gtk.Align.CENTER)
		self.canvas.set_valign(Gtk.Align.CENTER)

		p=self.focus_item.p
		it=Item(p)
		Gdk.cairo_set_source_pixbuf(cr, it.get_pixbuf(), 0, 0)
		cr.paint()
		sx1,sy1=self.selstart
		sx,sy=self.selend
		if sx1>sx:
			sx1,sx=sx,sx1
		if sy1>sy:
			sy1,sy=sy,sy1
		if self.selstart!=(None, None) and self.selend!=(None, None):
			xoff=self.selend[0]-self.selstart[0]
			yoff=self.selend[1]-self.selstart[1]
		else:
			xoff=0
			yoff=0

		for i,c in enumerate(p['children']):
			x1=(c['x1']-p['x1'])
			y1=(c['y1']-p['y1'])
			x2=(c['x2']-p['x1'])
			y2=(c['y2']-p['y1'])
			if i in self.selections:
				cr.set_source_rgba(0,0,255,255)
				if self.mode=='move':
					cr.rectangle(x1+xoff, y1+yoff, x2-x1, y2-y1)
				elif self.mode=='resize':
					xoff2=max(xoff,x1-x2)
					yoff2=max(yoff,y1-y2)
					cr.rectangle(x1, y1, x2-x1+xoff2, y2-y1+yoff2)
				else:
					cr.rectangle(x1, y1, x2-x1, y2-y1)
			else:
				cr.set_source_rgba(255,0,0,255)
				cr.rectangle(x1, y1, x2-x1, y2-y1)
			cr.stroke()
		if self.toggle_childrenpath.get_active():
			cr.set_source_rgba(0,255,0,255)
			for i,c in enumerate(p['children']):
				xa=(c['x1']+c['x2'])/2-p['x1']
				ya=(c['y1']+c['y2'])/2-p['y1']
				if i in self.selections:
					if self.mode=='move':
						xa+=xoff
						ya+=yoff
					elif self.mode=='resize':
						xoff2=max(xoff,x1-x2)
						yoff2=max(yoff,y1-y2)
						xa+=xoff2/2
						ya+=yoff2/2
				if i==0:
					cr.move_to(xa,ya)
				else:
					cr.line_to(xa,ya)
			cr.stroke()
			if self.selections:
				cr.set_line_width(3)
				cr.set_source_rgba(0,0,0,255)
				for i,c in enumerate(self.reordered_children()):
					xa=(c['x1']+c['x2'])/2-p['x1']
					ya=(c['y1']+c['y2'])/2-p['y1']
					if i in self.selections:
						if self.mode=='move':
							xa+=xoff
							ya+=yoff
						elif self.mode=='resize':
							xoff2=max(xoff,x1-x2)
							yoff2=max(yoff,y1-y2)
							xa+=xoff2/2
							ya+=yoff2/2
					if i==0:
						cr.move_to(xa,ya)
					else:
						cr.line_to(xa,ya)
				cr.stroke()
				cr.set_line_width(1)
		if self.selstart!=(None, None) and self.selend!=(None, None) and len(self.selections)==0:
			cr.set_source_rgba(255,0,255,255)
			cr.rectangle(sx1, sy1, sx-sx1, sy-sy1)
			cr.stroke()
			self.set_status('Box (%d,%d) -> (%d, %d)' % (sx1, sy1, sx, sy))
		elif self.mode=='resize':
			self.set_status('Resize (%d,%d)' % (xoff, yoff))
		elif self.mode=='move':
			self.set_status('Move (%d,%d)' % (xoff, yoff))

	def preview_draw(self, widget, cr):
		if not self.focus_item:
			return
		focus_p=self.focus_item.p
		if len(self.selections)!=1:
			return
		p=focus_p['children'][self.selections[0]]
		width=p['x2']-p['x1']
		height=p['y2']-p['y1']

		self.canvas.set_size_request(width, height)

		it=Item(focus_p)
		Gdk.cairo_set_source_pixbuf(cr, it.get_pixbuf(), focus_p['x1']-p['x1'], focus_p['y1']-p['y1'])
		cr.rectangle(0, 0, width, height)
		cr.fill()

	def zoom_fit(self, *arg):
		if not self.focus_item or not self.canvas:
			return
		p=self.focus_item.p
		workarea_window=self.builder.get_object('workarea_window')
		alloc=workarea_window.get_allocation()
		win_width=alloc.width
		win_height=alloc.height
		width=p['x2']-p['x1']
		height=p['y2']-p['y1']
		if width>win_width*0.8:
			self.zoom=(win_width*0.8/width)*100
		else:
			self.zoom=100
		self.canvas.queue_draw()

	def zoom_100(self, *arg):
		if not self.canvas:
			return
		self.zoom=100
		self.canvas.queue_draw()

	def zoom_in(self, *arg):
		if not self.canvas:
			return
		self.zoom+=5
		self.canvas.queue_draw()

	def zoom_out(self, *arg):
		if not self.canvas:
			return
		if self.zoom>5:
			self.zoom-=5
		self.canvas.queue_draw()

	def remove_item(self, *arg):
		if not self.focus_item:
			return
		items_list=self.builder.get_object("items_list")

		level_change=False
		focus_p=self.focus_item.p
		prev=self.focus_item.prev
		next=self.focus_item.next

		self.focus_item.prev=None
		self.focus_item.next=None
		items_list.remove(self.focus_item)

		if next:
			new_focus_widget=next
			next.prev=prev
			if prev:
				prev.next=next
		elif prev:
			new_focus_widget=prev
			prev.next=next
			if next:
				next.prev=prev
		else:
			level_change=True
			new_focus_widget=None
			self.focus_item=None
			workarea=self.builder.get_object("workarea")
			c=workarea.get_child()
			if c:
				workarea.remove(c)
				c.destroy()

		if focus_p:
			parent=focus_p['parent']
			if not parent:
				idx=self.clips.index(focus_p)
				del(self.clips[idx])
			else:
				idx=parent['children'].index(focus_p)
				del(parent['children'][idx])

		if new_focus_widget:
			click(new_focus_widget)
		if level_change:
			self.level_sanitize()

	def add_item(self, *arg):
		filec=Gtk.FileChooserDialog("Add", self.builder.get_object("main_window"), Gtk.FileChooserAction.OPEN, (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_ADD, Gtk.ResponseType.ACCEPT))
		filec.set_select_multiple(True)
		if Gtk.Dialog.run(filec)==Gtk.ResponseType.ACCEPT:
			cs=filec.get_filenames()
			cs.sort(natcmp)
			for path in cs:
				self.add_item_r(path)
			filec.destroy()
		else:
			filec.destroy()
			return
		self.level_sanitize()
		self.redraw_items_list()

	def add_item_r(self, path):
		if os.path.isdir(path):
			cs=os.listdir(path)
			cs.sort(natcmp)
			for c in cs:
				self.add_item_r(os.path.join(path,c))
		else:
			try:
				im=Image.open(path)
			except:
				return
			id_map[path]=md5.new(path).hexdigest()
			self.clips.append({'path':path,'x1':0,'y1':0,'x2':im.size[0],'y2':im.size[1],'children':[], 'tags':{}, 'parent':None, 'flags':[], 'reference':{}})
			del(im)

	def change_level(self, *arg):
		level=self.builder.get_object("level").get_active_text()
		if level!=self.curr_level and level:
			self.focus_field=(None, None)
			if self.focus_item:
				self.last_focus=self.focus_item.p
			self.last_level=self.curr_level
			self.curr_level=level
			self.redraw_items_list()

	def items_filter_apply(self, *arg):
		self.items_filter=CQL(self.builder.get_object("items_filter").get_text())
		if self.items_filter:
			self.redraw_items_list()
		else:
			self.set_status('Failed parsing filter')

	def redraw_items_list(self, *arg):
		if len(self.clips)==0 or not self.builder.get_object("level").get_active_text():
			return
		focus_p=None
		if self.focus_item:
			focus_p=self.focus_item.p
			self.focus_item.get_style_context().remove_class("darkback")
			self.focus_item.queue_draw()
			self.focus_item=None
		items_list=self.builder.get_object("items_list")
		for c in items_list.get_children():
			items_list.remove(c)
			c.destroy()
		flag=0
		s=self.clips
		for i in xrange(0,int(self.builder.get_object("level").get_active_text())):
			ns=[]
			for x in s:
				ns.extend(x['children'])
			s=ns
		last=None
		idx=0
		for p in s:
			if self.items_filter and not self.items_filter.eval(p):
				continue
			it=Item(p)
			tfile=it.get_thumbnail()
			evtbox=Gtk.EventBox()
			box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
			img=Gtk.Image.new_from_file(tfile)
			label=Gtk.Label(os.path.basename(p['path']))
			box.pack_start(img, False, False, 0)
			box.pack_start(label, False, False, 0)
			evtbox.add(box)
			if last:
				last.next=evtbox
			evtbox.p=p
			evtbox.prev=last
			evtbox.next=None
			evtbox.index=idx
			idx+=1
			evtbox.get_style_context().add_provider(self.css, 10)
			last=evtbox
			evtbox.connect("button-press-event", self.item_button_press)
			items_list.pack_start(evtbox, False, False, 5)
			evtbox.show_all()
			if not flag:
				if self.last_level and self.curr_level>self.last_level:
					t=p
					while t and not flag:
						if self.last_focus==t['parent']:
							flag=1
							self.focus_item=evtbox
							break
						t=t['parent']
				elif self.last_level and self.curr_level<self.last_level:
					s=[]
					s.extend(p['children'])
					while s and not flag:
						ns=[]
						for c in s:
							if self.last_focus==c:
								flag=1
								self.focus_item=evtbox
								break
							ns.extend(c['children'])
						s=ns
				elif focus_p==p:
					self.focus_item=evtbox
					flag=1
		self.items_number=idx
		if not self.focus_item:
			cl=items_list.get_children()
			if cl:
				self.focus_item=cl[-1]

		if self.focus_item:
			click(self.focus_item)

	def set_children_order(self, *arg):
		if not self.focus_item:
			return
		if not self.toggle_childrenpath:
			self.set_status("Please enable areas path display")
			return
		p=self.focus_item.p
		p['children']=self.reordered_children()
		self.selections=range(0,len(p['children']))
		self.canvas.queue_draw()

	def reordered_children(self):
		if not self.focus_item:
			return
		p=self.focus_item.p
		r=[]
		for i in self.selections:
			r.append(p['children'][i])
		for i,c in enumerate(p['children']):
			if i not in self.selections:
				r.append(c)
		return r

	def autoscroll(self):
		items_list=self.builder.get_object("items_list")
		focus_widget=self.focus_item
		alloc=items_list.get_allocation()
		x,y=focus_widget.translate_coordinates(items_list, 0, 0)
		scr=self.builder.get_object("scroll_items_list")
		vadj=scr.get_vadjustment()
		vadj.set_lower(0)
		vadj.set_upper(alloc.height)
		alloc=scr.get_allocation()
		vadj.set_value(y-alloc.height*0.3)

	def level_sanitize(self):
		level=self.builder.get_object("level")
		l=0
		s=self.clips
		while s:
			l+=1
			ns=[]
			for x in s:
				ns.extend(x['children'])
			s=ns
		try:
			active=int(level.get_active_text())
		except:
			active=0
		level.remove_all()
		for i in xrange(0,l):
			level.append_text(str(i))
		if active<l:
			level.set_active(active)
		else:
			level.set_active(l-1)

	def item_button_press(self, obj, evt):
		if self.focus_item:
			self.focus_item.get_style_context().remove_class("darkback")
			self.focus_item.queue_draw()
		if evt.button==1 and evt.type==Gdk.EventType.BUTTON_PRESS:
			if obj!=self.focus_item:
				try:
					p=self.focus_item.p
					p['flags'].remove('CHANGED')
				except:
					pass
			self.set_status("Item: %d/%d" % (obj.index+1, self.items_number))
			p=obj.p
			self.focus_item=obj
			obj.get_style_context().add_class("darkback")
			obj.queue_draw()
			GObject.idle_add(self.autoscroll)

			self.selections=[]
			self.tags_refresh()
			workarea=self.builder.get_object('workarea')
			c=workarea.get_child()
			if c:
				workarea.remove(c)
				c.destroy()
			canvas=Gtk.DrawingArea()
			self.canvas=canvas
			canvas.set_can_focus(True)
			workarea.add(canvas)
			canvas.connect("draw", self.canvas_draw)
			canvas.show()

			preview=self.builder.get_object('preview')
			c=preview.get_child()
			if c:
				preview.remove(c)
				c.destroy()
			canvas=Gtk.DrawingArea()
			self.preview_canvas=canvas
			preview.add(canvas)
			canvas.connect("draw", self.preview_draw)
			canvas.show()
			self.zoom_fit()
			if self.toggle_ocr.get_active():
				if self.toggle_collation.get_active():
					for cp in p['children']:
						if cp['tags'].get('text', None):
							continue
						cit=Item(cp)
						tempdir=cit.get_ocr_tempdir()
						if not os.path.exists(tempdir):
							os.makedirs(tempdir)
						im=cit.get_pil_cropped()
						im.save(os.path.join(tempdir, "clip.png"))
						del(im)
						os.chdir(tempdir)
						subprocess.call(["tesseract", "clip.png", "out"])
						text=open("out.txt").read().rstrip().decode("utf-8")
						for rx,r in self.regex:
							text2=re.sub(rx, r, text)
							print text.encode("utf-8"), '|', rx.encode("utf-8"), '|', r.encode("utf-8"), '|', text2.encode("utf-8")
							text=text2
						cp['tags']['text']=text
						if 'text' not in self.tags:
							self.tags.append('text')
						cp['flags'].append('CHANGED')
					self.selections.append(0)
					self.canvas.queue_draw()
				else:
					if p['tags'].get('text', None):
						return
					it=Item(p)
					tempdir=it.get_ocr_tempdir()
					if not os.path.exists(tempdir):
						os.makedirs(tempdir)
					im=it.get_pil_cropped()
					im.save(os.path.join(tempdir, "clip.png"))
					del(im)
					os.chdir(tempdir)
					subprocess.call(["tesseract", "clip.png", "out"])
					p['tags']['text']=open("out.txt").read().rstrip()
					if 'text' not in self.tags:
						self.tags.append('text')
					self.level_sanitize()
					p['flags'].append('CHANGED')
				self.tags_refresh()
			# GObject.idle_add(lambda: self.canvas.grab_focus())

	def tags_refresh(self, *arg):
		if not self.focus_item:
			return
		self.builder.get_object('tags_pane').show_all()

		tagsbox=self.builder.get_object('tags')
		c=tagsbox.get_child()
		if c:
			tagsbox.remove(c)
		collation_editor=self.builder.get_object("collation_editor")
		collation_editor.master=None
		collation_editor.set_text("")

		focus_p=self.focus_item.p
		t=focus_p
		tags={}
		while t:
			for tag in t['tags']:
				if tag not in tags:
					tags[tag]=t['tags'][tag]
			t=t['parent']
		for tag in self.tags:
			if tag not in tags:
				tags[tag]=""

		tags_table=Gtk.Grid()
		tagsbox.add(tags_table)
		print self.focus_field
		for i,tag in enumerate(self.tags):
			text=Gtk.Entry()
			text.set_text(tags[tag])
			text.connect('changed', self.set_tag, (focus_p, tag))
			text.connect("focus-in-event", self.entry_focus, ('p', focus_p, tag))
			if self.focus_field[0]=='p' and self.focus_field[1]==tag:
				self.focus_entry=text
			label=Gtk.Label(tag)
			button=Gtk.Button()
			btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_CLEAR, Gtk.IconSize.BUTTON)
			button.set_image(btn_img)
			button.connect("clicked", self.clear_tag, (focus_p, tag))
			tags_table.attach(label,0,i,1,1)
			tags_table.attach(text,1,i,1,1)
			tags_table.attach(button,2,i,1,1)
		tagsbox.show_all()
		GObject.idle_add(self.autofocus)
		self.child_tags_refresh()

	def child_tags_refresh(self, *arg):
		if not self.focus_item:
			return

		tagsbox=self.builder.get_object('child_tags')
		c=tagsbox.get_child()
		if c:
			tagsbox.remove(c)

		if len(self.selections)!=1:
			return

		focus_p=self.focus_item.p
		p=focus_p['children'][self.selections[0]]
		t=p
		tags={}
		while t:
			for tag in t['tags']:
				if tag not in tags:
					tags[tag]=t['tags'][tag]
			t=t['parent']
		for tag in self.tags:
			if tag not in tags:
				tags[tag]=""
		tags_table=Gtk.Grid()
		tagsbox.add(tags_table)
		for i,tag in enumerate(self.tags):
			text=Gtk.Entry()
			text.set_text(tags[tag])
			text.connect('changed', self.set_tag, (p, tag))
			text.connect("focus-in-event", self.entry_focus, ('c', p, tag))

			if self.focus_field[0]=='c' and self.focus_field[1]==tag:
				self.focus_entry=text
			label=Gtk.Label(tag)
			button=Gtk.Button()
			btn_img=Gtk.Image.new_from_stock(Gtk.STOCK_CLEAR, Gtk.IconSize.BUTTON)
			button.set_image(btn_img)
			button.connect("clicked", self.clear_tag, (p,tag))
			tags_table.attach(label,0,i,1,1)
			tags_table.attach(text,1,i,1,1)
			tags_table.attach(button,2,i,1,1)
		tagsbox.show_all()
		self.collation_cb(None)
		GObject.idle_add(self.autofocus)

	def autofocus(self, *arg):
		print "autofocus A"
		if self.focus_entry:
			print "autofocus B"
			if not self.focus_entry.get_text():
				print "autofocus D"
				auto_fill=self.builder.get_object("auto_fill").get_active_text()
				if auto_fill=="Clipboard":
					self.focus_entry.paste_clipboard()
					GObject.idle_add(self.autofocus2)
				print "autofocus F"
				self.focus_entry.grab_focus()
				print "autofocus G"
			else:
				print "autofocus C"
				self.focus_entry.grab_focus()
				self.focus_entry=None

	def autofocus2(self, *arg):
		if not self.focus_entry:
			return
		self.focus_entry.set_position(-1)
		self.focus_entry=None

	def entry_focus(self, obj, evt, data, *arg):
		t,item,tag=data
		self.focus_field=(t,tag)
		print "set", self.focus_field
		self.collation_cb(obj)

	def set_tag(self, obj, data):
		item,tag=data
		item['tags'][tag]=obj.get_buffer().get_text()
		if 'CHANGED' not in item['flags']:
			item['flags'].append('CHANGED')
		if item['parent']:
			if 'CHANGED' not in item['parent']['flags']:
				item['parent']['flags'].append('CHANGED')
		self.collation_cb(obj)

	def collation_cb(self, obj, *arg):
		if self.toggle_collation.get_active() and self.focus_field and self.focus_field[0]=='c':
			self.builder.get_object("editor_label").set_text(self.focus_field[1])
			self.builder.get_object("collation_window").show()
			self.builder.get_object("collation_editor").master=obj
			if not self.signal_mask and obj:
				GObject.idle_add(self.focus_collation_editor)
				self.signal_mask=True
				self.builder.get_object("collation_editor").set_text(obj.get_text())
				self.signal_mask=False
		else:
			self.builder.get_object("collation_window").hide()

	def focus_collation_editor(self):
		self.builder.get_object("collation_editor").grab_focus()
		GObject.idle_add(self.focus_collation_editor2)

	def focus_collation_editor2(self, *arg):
		self.builder.get_object("collation_editor").set_position(0)

	def collation_editor_changed(self, obj, *arg):
		master=obj.master
		if master and not self.signal_mask:
			self.signal_mask=True
			master.set_text(obj.get_text())
			self.signal_mask=False

	def clear_tag(self, obj, data):
		item,tag=data
		del(item['tags'][tag])
		self.tags_refresh()

	def workarea_mouse(self, obj, evt):
		if not self.canvas:
			return
		self.focus_field=(None, None)
		self.canvas.grab_focus()
		factor=self.zoom*0.01
		evtx,evty=self.builder.get_object('workarea').translate_coordinates(self.canvas, evt.x, evt.y)
		x=evtx/factor
		y=evty/factor
		p=self.focus_item.p
		if str(type(evt))==repr(Gdk.EventButton):
			if evt.button==1 and evt.type==Gdk.EventType.BUTTON_PRESS:
				self.selstart=(x,y)
				if not len(self.selections):
					self.mode='rectangle'
				else:
					for i in self.selections:
						c=p['children'][i]
						if x+p['x1']>c['x1'] and x+p['x1']<c['x2'] and y+p['y1']>c['y1'] and y+p['y1']<c['y2']:
							self.mode='move'
							break
					else:
						self.mode='resize'
			elif evt.button==1 and evt.type==Gdk.EventType.BUTTON_RELEASE:
				x1,y1=self.selstart
				if (x1,y1)==(None, None):
					return
				if x1==x and y1==y:
					for i,c in enumerate(p['children']):
						if x+p['x1']>c['x1'] and x+p['x1']<c['x2'] and y+p['y1']>c['y1'] and y+p['y1']<c['y2']:
							if i in self.selections:
								self.selections.remove(i)
							else:
								self.selections.append(i)
					self.child_tags_refresh()
					self.set_status('Area: %d Select: %s' % (len(p['children']), ', '.join([str(i+1) for i in self.selections])))
				elif self.mode=='rectangle':
					if x1>x:
						x1,x=x,x1
					if y1>y:
						y1,y=y,y1
					x1=max(x1,0)
					y1=max(y1,0)
					x=min(x,p['x2']-p['x1'])
					y=min(y,p['y2']-p['y1'])
					if x-x1>5 and y-y1>5:
						p['children'].append({'path':p['path'], 'x1':int(x1+p['x1']), 'y1':int(y1+p['y1']), 'x2':int(x+p['x1']), 'y2':int(y+p['y1']), 'children':[], 'parent':p, 'tags':{}, 'flags':[], 'reference':{}})
					self.level_sanitize()
				elif self.mode=='move':
					xoff=int(self.selend[0]-self.selstart[0])
					yoff=int(self.selend[1]-self.selstart[1])
					todo=[]
					for i in self.selections:
						todo.append(p['children'][i])
					while todo:
						delete=[]
						newtodo=[]
						for c in todo:
							x1=c['x1']+xoff
							y1=c['y1']+yoff
							x=c['x2']+xoff
							y=c['y2']+yoff
							x1=max(x1,c['parent']['x1'])
							y1=max(y1,c['parent']['y1'])
							x=min(x,c['parent']['x2'])
							y=min(y,c['parent']['y2'])
							c['x1']=min(x1,c['parent']['x2'])
							c['y1']=min(y1,c['parent']['y2'])
							c['x2']=max(x,c['parent']['x1'])
							c['y2']=max(y,c['parent']['y1'])
							if abs(x-x1)<=1 or abs(y-y1)<=1:
								delete.append(c)
							else:
								newtodo.extend(c['children'])
						todo=newtodo
						for c in delete:
							if c['parent']:
								c['parent']['children'].remove(c)
							else:
								self.clips.remove(c)
					self.level_sanitize()
				elif self.mode=='resize':
					xoff=int(self.selend[0]-self.selstart[0])
					yoff=int(self.selend[1]-self.selstart[1])
					todo=[]
					delete=[]
					self.selections.sort()
					self.selections.reverse()
					for i in self.selections:
						c=p['children'][i]
						xoff2=max(xoff,c['x1']-c['x2'])
						yoff2=max(yoff,c['y1']-c['y2'])
						x1=c['x1']
						y1=c['y1']
						x=c['x2']+xoff2
						y=c['y2']+yoff2
						c['x1']=max(x1,p['x1'])
						c['y1']=max(y1,p['y1'])
						c['x2']=min(x,p['x2'])
						c['y2']=min(y,p['y2'])
						if abs(x-x1)<=1 or abs(y-y1)<=1:
							delete.append(c)
						else:
							todo.extend(c['children'])
					if delete:
						self.selections=[]
						self.child_tags_refresh()
					for c in delete:
						if c['parent']:
							c['parent']['children'].remove(c)
						else:
							self.clips.remove(c)
					self.edge_limiter(todo)
				self.selstart=(None, None)
				self.selend=(None, None)
				self.mode=None
				self.canvas.queue_draw()
				self.preview_canvas.queue_draw()
			elif evt.button==3:
				self.selstart=(None, None)
		elif str(type(evt))==repr(Gdk.EventMotion):
			self.selend=(x,y)
			self.canvas.queue_draw()
		elif str(type(evt))==repr(Gdk.EventScroll) and evt.state & Gdk.ModifierType.CONTROL_MASK:
			if evt.direction==Gdk.ScrollDirection.UP:
				self.zoom+=5
			elif evt.direction==Gdk.ScrollDirection.DOWN:
				self.zoom-=5
			self.canvas.queue_draw()
			return False

	def edge_limiter(self, todo):
		while todo:
			delete=[]
			newtodo=[]
			for c in todo:
				x1=c['x1']
				y1=c['y1']
				x=c['x2']
				y=c['y2']
				if x1>x:
					x1,x=x,x1
				if y1>y:
					y1,y=y,y1
				c['x1']=max(x1,c['parent']['x1'])
				c['y1']=max(y1,c['parent']['y1'])
				c['x2']=min(x,c['parent']['x2'])
				c['y2']=min(y,c['parent']['y2'])
				if abs(x-x1)<=1 or abs(y-y1)<=1:
					delete.append(c)
				else:
					newtodo.extend(c['children'])
			todo=newtodo
			for c in delete:
				if c['parent']:
					c['parent']['children'].remove(c)
				else:
					self.clips.remove(c)
