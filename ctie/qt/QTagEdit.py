from PyQt5.QtWidgets import *
from PyQt5 import QtGui
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class QTagEdit(QPlainTextEdit):
    focusIn = pyqtSignal()
    focusOut = pyqtSignal()

    def __init__(self):
        QPlainTextEdit.__init__(self)
        font = QtGui.QFont("Consolas")
        font.setStyleHint(QtGui.QFont.TypeWriter)
        self.blank = True
        self.blocked = False
        self.setFont(font)

        self.textChanged.connect(self.onTextChanged)

    def focusInEvent(self, event):
        QPlainTextEdit.focusInEvent(self, event)
        self.focusIn.emit()

    def focusOutEvent(self, event):
        QPlainTextEdit.focusOutEvent(self, event)
        self.focusOut.emit()

    def setPlainText(self, text):
        QPlainTextEdit.setPlainText(self, text)
        self.onTextChanged()

    def setPlaceholderText(self, text):
        QPlainTextEdit.setPlaceholderText(self, text)
        self.updateHeight()

    def onTextChanged(self):
        if self.blocked:
            return
        blank = not self.toPlainText()
        if self.blank != blank:
            self.blank = blank
            self.updateHeight()

    def updateHeight(self):
        currText = self.toPlainText()
        if currText:
            self.setFixedHeight(self.getContentHeight())
        else:
            self.blocked = True
            QPlainTextEdit.setPlainText(self, self.placeholderText())
            self.setFixedHeight(self.getContentHeight())
            QPlainTextEdit.setPlainText(self, "")
            self.blocked = False

    # https://stackoverflow.com/questions/45028105/get-the-exact-height-of-qtextdocument-in-pixels
    def getContentHeight(self):
        doc = self.document()
        layout = doc.documentLayout()
        h = 0
        b = doc.begin()
        while b != doc.end():
            h += layout.blockBoundingRect(b).height()
            b = b.next()

        # magic formula: I do not know why the document margin is already
        # once included in the height of the last block, and I do not know
        # why there must be the number 1 at the end... but it works
        return h + doc.documentMargin() + 2 * self.frameWidth() + 1
