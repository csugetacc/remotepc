import sys
import threading
from PySide6 import QtCore, QtWidgets, QtGui

import client
import server

# page for running client program 
class ClientPage(QtWidgets.QWidget):

    def __init__(self, stacked_widget):
        super().__init__()

        self.stacked_widget = stacked_widget

        self.host_label = QtWidgets.QLabel("Host: ")
        self.set_host = QtWidgets.QLineEdit()
        self.button = QtWidgets.QPushButton("Connect")

        self.back_button = QtWidgets.QPushButton("Back")
        self.back_button.setFixedSize(80, 30)

        # video display box
        self.video_box = QtWidgets.QLabel()
        self.video_box.setAlignment(QtCore.Qt.AlignCenter)
        self.video_box.setStyleSheet("background:#111; color:#aaa;")
        self.video_box.setText("Video feed will appear here")
        self.video_box.setMouseTracking(True)       # track mouse within video box
        self.video_box.setFocusPolicy(QtCore.Qt.StrongFocus)    # set keyboard focus
        self.video_box.installEventFilter(self)     # allows intercepting inputs 
        
        # align host text and input box
        self.host_line = QtWidgets.QHBoxLayout()
        self.host_line.addWidget(self.host_label)
        self.host_line.addWidget(self.set_host)

        # page layout 
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.addWidget(self.back_button, alignment = QtCore.Qt.AlignRight)
        self.layout.addWidget(self.video_box)
        self.layout.addLayout(self.host_line)
        self.layout.addWidget(self.button)

        # button presses
        self.button.clicked.connect(self.start_client)
        self.back_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(0))

    # runs client program in seperate thread
    def start_client(self):
        
        name = self.set_host.text().strip()

        # check inputed device name
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing name", "Enter a host device name.")
            return

        # convert name to ip  
        ip = client.getip(name)

        # check if ip exists 
        if not ip:
            QtWidgets.QMessageBox.warning(self, "Unknown host", f"No IP found for '{name}' in hosts.csv")
            return

        # create qthread and client worker objects
        self.client_thread = QtCore.QThread(self)   # for event loop container
        self.client_worker = client.ClientWorker(ip)    # for networking loop

        # move worker to run in the client thread
        self.client_worker.moveToThread(self.client_thread)

        # connect signals
        self.client_thread.started.connect(self.client_worker.start)
        self.client_worker.frameReady.connect(self.Qt_frame)
        self.client_worker.statusText.connect(self.video_box_status_text)
        self.client_worker.closed.connect(self.close_client)

        # shutdown
        self.client_thread.finished.connect(self.client_thread.deleteLater)

        # start thread
        self.client_thread.start()


    def eventFilter(self, obj, event):

        if obj is self.video_box and hasattr(self, "client_worker"):

            mouse_event = event.type()

            # collect mose movement
            if mouse_event == QtCore.QEvent.MouseMove:   
                pos = event.globalPosition().toPoint()
                self.client_worker.mouse_move(pos.x(), pos.y())
                
            # collect mouse click
            elif mouse_event == QtCore.QEvent.MouseButtonPress:
                button = event.button()
                which = 'left' if button == QtCore.Qt.LeftButton else 'right'
                self.client_worker.mouse_click(which)
                self.video_box.setFocus()   # sets focus for keys

            # collect mouse release
            elif mouse_event == QtCore.QEvent.MouseButtonRelease:
                button = event.button()
                which = 'left' if button == QtCore.Qt.LeftButton else 'right'
                self.client_worker.mouse_release(which)

        return super().eventFilter(obj, event)


    # display qimage as pixmap 
    @QtCore.Slot(QtGui.QImage)
    def Qt_frame(self, qimg: QtGui.QImage):

        self.video_box.setPixmap(QtGui.QPixmap.fromImage(qimg))     # set up display

        # collect video box dimensions
        top_left = self.video_box.mapToGlobal(QtCore.QPoint(0, 0))  
        w = self.video_box.width()
        h = self.video_box.height()

        if hasattr(self, "client_worker"):  # prevent attribute error crash
            self.client_worker.set_window_rect(top_left.x(), top_left.y(), w, h)


    # changes status text for video box 
    @QtCore.Slot(str)
    def video_box_status_text(self, text: str):
        if text:
            self.video_box.setText(text)


    # close out client
    @QtCore.Slot()
    def close_client(self):
        if self.client_thread.isRunning() and hasattr(self, "client_thread"):
            self.client_thread.quit()
            self.client_thread.wait(500)

    
    # remap special keys
    Qt_key = {
        QtCore.Qt.Key_Escape:   'esc',
        QtCore.Qt.Key_Tab:      'tab',
        QtCore.Qt.Key_Backspace:'backspace',
        QtCore.Qt.Key_Return:   'enter',
        QtCore.Qt.Key_Enter:    'enter',
        QtCore.Qt.Key_Space:    'space',
        QtCore.Qt.Key_Left:     'left',
        QtCore.Qt.Key_Right:    'right',
        QtCore.Qt.Key_Up:       'up',
        QtCore.Qt.Key_Down:     'down',
        QtCore.Qt.Key_Shift:    'shift',
        QtCore.Qt.Key_Control:  'ctrl',
        QtCore.Qt.Key_Alt:      'alt',
        QtCore.Qt.Key_Meta:     'cmd',
    }

    def key_to_name(self, event: QtGui.QKeyEvent) -> str | None:

        if event.isAutoRepeat():    # ignore auto repeats 
            return None

        key = event.key()

        # basic inputs
        ch = event.text()
        if ch:
            return ch if len(ch) > 1 else ch.lower()     # standardize keys

        # remap special keys using legend 
        if key in Qt_key:
            return Qt_key[k]

        # function keys
        if QtCore.Qt.Key_F1 <= key <= QtCore.Qt.Key_F24:
            name = key - QtCore.Qt.Key_F1 + 1
            return f"f{name}"

        return None

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if hasattr(self, "client_worker"):
            name = self.key_to_name(event)
            if name:
                self.client_worker.key_press(name)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        if hasattr(self, "client_worker"):
            name = self.key_to_name(event)
            if name:
                self.client_worker.key_release(name)


# page for running server function
class ServerPage(QtWidgets.QWidget):
    def __init__(self, stacked_widget):
        super().__init__()

        self.stacked_widget = stacked_widget

        # buttons
        self.back_button = QtWidgets.QPushButton("Back")
        self.back_button.setFixedSize(80, 30)

        self.start_button = QtWidgets.QPushButton("Start Server")
        self.stop_button = QtWidgets.QPushButton("Stop Server")
        self.stop_button.setEnabled(False)  # grayed out untill start server is pressed

        self.status = QtWidgets.QLabel("Server is stopped.", alignment=QtCore.Qt.AlignCenter)

        # align start and stop buttons
        self.button_line = QtWidgets.QHBoxLayout()
        self.button_line.addWidget(self.start_button)
        self.button_line.addWidget(self.stop_button)

        # page layout 
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.addWidget(self.back_button, alignment = QtCore.Qt.AlignRight)
        self.layout.addWidget(self.status)
        self.layout.addLayout(self.button_line) 

        # button presses
        self.back_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(0))
        self.start_button.clicked.connect(self.start_server)
        self.stop_button.clicked.connect(self.stop_server)
        
    # run server program in seperate thread
    def start_server(self):

        self._server_thread = threading.Thread(target=server.server_program, daemon=True)
        self._server_thread.start()
        self.status.setText("Server listening on 0.0.0.0:5000/5001...")

        # swap presed button
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    # not implemented
    def stop_server(self):
        QtWidgets.QMessageBox.information(
            self,
            "Stop Server",
            "Stop server not implemented"
        )
        self.stop_button.setEnabled(False)     


# main page
class MainMenu(QtWidgets.QWidget):
    def __init__(self, stacked_widget):
        super().__init__()

        self.stacked_widget = stacked_widget

        self.title = QtWidgets.QLabel("Select Mode", alignment=QtCore.Qt.AlignCenter)
        self.title.setStyleSheet("font-size: 24px; margin-bottom: 20px;")

        # buttons
        self.client_button = QtWidgets.QPushButton("Client")
        self.client_button.setFixedSize(200, 50)
        self.server_button = QtWidgets.QPushButton("Server")
        self.server_button.setFixedSize(200, 50)

        # page layout
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.title)
        self.layout.addWidget(self.client_button)
        self.layout.addWidget(self.server_button)

        # button presses
        self.client_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(1))
        self.server_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(2))


if __name__ == "__main__":
    # define app
    app = QtWidgets.QApplication([])

    stacked_widget = QtWidgets.QStackedWidget()
    main_menu = MainMenu(stacked_widget)
    client_page = ClientPage(stacked_widget)
    server_page = ServerPage(stacked_widget)

    # pages 
    stacked_widget.addWidget(main_menu)     # 0
    stacked_widget.addWidget(client_page)   # 1
    stacked_widget.addWidget(server_page)   # 2

    stacked_widget.setCurrentIndex(0)   # start on main_menue page
    stacked_widget.resize(800, 600)
    stacked_widget.show()

    sys.exit(app.exec())