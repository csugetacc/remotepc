import sys
import threading
import os
import csv
import socket

from PySide6 import QtCore, QtWidgets, QtGui

import client
import server

# set values for streaming 
FPS = 15
SCALE = .6
JPEG_QUALITY = 70


# page for running client program 
class ClientPage(QtWidgets.QWidget):

    def __init__(self, stacked_widget):
        super().__init__()

        self.stacked_widget = stacked_widget

        # hostname input
        self.host_label = QtWidgets.QLabel("Host: ")
        self.set_host = QtWidgets.QLineEdit()

        self.transfer_file = QtWidgets.QPushButton("Transfer Files")

        # public/private ip sellect
        self.ip_type_label = QtWidgets.QLabel("IP type: ")
        self.ip_type_menue = QtWidgets.QComboBox()
        self.ip_type_menue.addItems(["Auto", "Private", "Public"])

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
        self.video_box.setScaledContents(True)    # allow resizeing image
        self.video_box.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)  # unlock horizontal and vertical axsises 

        
        # align host text and input box
        self.host_line = QtWidgets.QHBoxLayout()
        self.host_line.addWidget(self.host_label)
        self.host_line.addWidget(self.set_host)

        # aling ip type info
        self.ip_type_line = QtWidgets.QHBoxLayout()
        self.ip_type_line.addWidget(self.ip_type_label)
        self.ip_type_line.addWidget(self.ip_type_menue)
        self.ip_type_line.addItem(QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum))        
        self.ip_type_line.addWidget(self.transfer_file)    # shoving this here
        # fix spacing of these items
        self.ip_type_line.setStretch(0, 0)
        self.ip_type_line.setStretch(1, 1)
        self.ip_type_line.setStretch(2, 1)
        self.ip_type_line.setStretch(3, 1)

        # page layout 
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.addWidget(self.back_button, alignment = QtCore.Qt.AlignRight)
        self.layout.addWidget(self.video_box)
        self.layout.addLayout(self.host_line)
        self.layout.addLayout(self.ip_type_line)
        self.layout.addWidget(self.button)

        # button presses
        self.button.clicked.connect(self.start_client)
        self.back_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(0))
        self.transfer_file.clicked.connect(self.innitate_transfer)


    # runs client program in seperate thread
    def start_client(self):
        
        name = self.set_host.text().strip()

        # check inputed device name
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing name", "Enter a host device name.")
            return

        # adjust to user preference 
        mode = self.ip_type_menue.currentText()
        if mode == "Private":
            use_public = False
        elif mode == "Public":
            use_public = True
        else:
            use_public = None

        # convert name to ip  
        ip = client.getip(name, use_public = use_public)

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

        # set up display
        pixmap = QtGui.QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(self.video_box.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)    # scale video to window size
        self.video_box.setPixmap(scaled)     

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
        QtCore.Qt.Key_Delete:   'delete',
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

        # remap special keys using legend 
        if key in self.Qt_key:
            return self.Qt_key[key]

        # basic inputs
        ch = event.text()
        if ch:
            return ch if len(ch) > 1 else ch.lower()     # standardize keys

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


    def innitate_transfer(self):

        # ensure the client is connected to the server
        if not hasattr(self, "client_worker") or not self.client_worker.control_socket:
            QtWidgets.QMessageBox.warning(self, "Not connected", "You must connect to a host before transferring files.")
            return

        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select file to send", "", "All Files (*.*)")

        # if user does not give input cancel
        if not path:
            return

        # start file send process
        self.client_worker.send_file(path)


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

        self.server_thread = threading.Thread(target=server.server_program, daemon=True, args=(FPS, SCALE, JPEG_QUALITY))
        self.server_thread.start()
        self.status.setText("Server listening on 0.0.0.0:5000/5001...")

        # swap presed button
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def stop_server(self):
        server.stop_server()
        self.status.setText("Server stopping...")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
  


# devices page
class DevicePage(QtWidgets.QWidget):
    def __init__(self, stacked_widget):
        super().__init__()

        self.stacked_widget = stacked_widget

        # buttons
        self.back_button = QtWidgets.QPushButton("Back")
        self.back_button.setFixedSize(80, 30)

        self.title = QtWidgets.QLabel("Devices", alignment=QtCore.Qt.AlignCenter)

        # csv table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Hostname", "Private IP", "Public IP"])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

        # display local device info
        self.local_private = self.get_local_private_ip()
        self.local_public = self.get_local_public_ip()
        local_private_text = self.local_private if self.local_private else "unknown"
        local_public_text = self.local_public if self.local_public else "unknown"
        self.local_label = QtWidgets.QLabel(f"This device - Private: {local_private_text}   Public: {local_public_text}")

        self.name_input = QtWidgets.QLineEdit()
        self.private_input = QtWidgets.QLineEdit()
        self.public_input = QtWidgets.QLineEdit()

        ip_box = QtWidgets.QFormLayout()
        ip_box.addRow("Hostname:", self.name_input)
        ip_box.addRow("Private IP:", self.private_input)
        ip_box.addRow("Public IP:", self.public_input)

        self.ip_button = QtWidgets.QPushButton("Autofill IP")
        self.add_button = QtWidgets.QPushButton("Add device")
        self.delete_button = QtWidgets.QPushButton("Remove device")
        self.refresh_button = QtWidgets.QPushButton("Refresh")

        buttons_line = QtWidgets.QHBoxLayout()
        buttons_line.addWidget(self.ip_button)
        buttons_line.addWidget(self.add_button)
        buttons_line.addWidget(self.delete_button)
        buttons_line.addWidget(self.refresh_button)

        # page layout 
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.back_button, alignment=QtCore.Qt.AlignRight)
        layout.addWidget(self.title, alignment=QtCore.Qt.AlignCenter)
        layout.addWidget(self.table)
        layout.addWidget(self.local_label)
        layout.addLayout(ip_box)
        layout.addLayout(buttons_line)

        # connect signals
        self.back_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(0))
        self.ip_button.clicked.connect(self.fill_local_ips)
        self.add_button.clicked.connect(self.add_device)
        self.delete_button.clicked.connect(self.delete_device)
        self.refresh_button.clicked.connect(self.load_devices)

        # initial load
        self.load_devices()

    # load info from hosts.csv
    def load_devices(self):
        self.table.setRowCount(0)

        if not os.path.exists("hosts.csv"):
            return

        with open("hosts.csv", newline="") as host_file:
            reader = csv.DictReader(host_file)

            for row_idx, row in enumerate(reader):      # get row value and index
                self.table.insertRow(row_idx)

                for col, key in enumerate(("hostname", "privateip", "publicip")):   
                    value = row.get(key, "")    # convert key to readable value
                    item = QtWidgets.QTableWidgetItem(value)
                    self.table.setItem(row_idx, col, item)

    # add device to hosts.csv
    def add_device(self):

        # get values from user
        name = self.name_input.text().strip()
        private_ip = self.private_input.text().strip()
        public_ip = self.public_input.text().strip()

        # warn if no name inputed (no ip ok)
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing hostname", "Enter a hostname.")
            return

        # set value if the csv has not been setup
        new_file = not os.path.exists("hosts.csv")

        # open or create file
        with open("hosts.csv", "a", newline="") as host_file:
            writer = csv.writer(host_file)

            # add headder
            if new_file:
                writer.writerow(["hostname", "privateip", "publicip"])
            
            # write inputed values
            writer.writerow([name, private_ip, public_ip])

        # clear and load inputs
        self.name_input.clear()
        self.private_input.clear()
        self.public_input.clear()
        self.load_devices()

    # delete device from hosts.csv
    def delete_device(self):

        # get selected name from menue
        row = self.table.currentRow()

        if row < 0:
            QtWidgets.QMessageBox.warning(self, "No selection", "Select a device in the table to remove.")
            return

        name_item = self.table.item(row, 0)
        if not name_item:
            return

        name = name_item.text().strip()

        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing hostname", "Enter a hostname to remove.")
            return

        if not os.path.exists("hosts.csv"):
            QtWidgets.QMessageBox.warning(self, "No hosts detected.")
            return

        kept_rows = []     # store rows to be kept
        removed = False

        # cycle through rows and mark for removal
        with open("hosts.csv", newline="") as host_file:
            reader = csv.DictReader(host_file)
            fieldnames = reader.fieldnames or ["hostname", "privateip", "publicip"]

            for row in reader:
                if row.get("hostname", "").strip() == name:
                    removed = True
                else:
                    kept_rows.append(row)

        if not removed:
            QtWidgets.QMessageBox.information(self, "Not found", f"No entry found with hostname '{name}'.")
            return

        # write back kept rows
        with open("hosts.csv", "w", newline="") as host_file:
            writer = csv.DictWriter(host_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(kept_rows)

        # refresh table
        self.load_devices()
        self.name_input.clear()
        self.private_input.clear()
        self.public_input.clear()

        QtWidgets.QMessageBox.information(self, "Removed", f"Device '{name}' has been removed.")


    # populate ip fields
    def fill_local_ips(self):
        self.private_input.setText(self.local_private or "")
        self.public_input.setText(self.local_public or "")

    # best guess at local ip
    @staticmethod
    def get_local_private_ip() -> str:

        try:
            # Source - https://stackoverflow.com/a
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
            s.close()
                
        except OSError:     # if this errors print a blank
            return 

    # not implemented 
    @staticmethod
    def get_local_public_ip() -> str:
        return 


class SettingsPage(QtWidgets.QWidget):
    def __init__(self, stacked_widget):
        super().__init__()

        self.stacked_widget = stacked_widget

        # buttons
        self.back_button = QtWidgets.QPushButton("Back")
        self.back_button.setFixedSize(80, 30)

        self.top_line = QtWidgets.QHBoxLayout()
        self.top_line.addWidget(self.back_button, alignment=QtCore.Qt.AlignRight)

        self.title = QtWidgets.QLabel("Settings", alignment=QtCore.Qt.AlignCenter)

        self.resolution_menue = QtWidgets.QComboBox()

        # options for resolution scale
        self.resolution_options = [
            ("High (1.0x - full)", 1.0),
            ("Medium (0.75x)", 0.75),
            ("Low (0.5x)", 0.5),
            ("Very Low (0.25x)", 0.25),
        ]
        for label, _ in self.resolution_options:
            self.resolution_menue.addItem(label)

        # spin box for fps value
        self.fps_spin = QtWidgets.QSpinBox()
        self.fps_spin.setRange(5, 60)
        self.fps_spin.setSingleStep(5)  # ammount the arrows move value

        form = QtWidgets.QFormLayout()
        form.addRow("Resolution scale:", self.resolution_menue)
        form.addRow("Framerate (FPS):", self.fps_spin)

        self.save_button = QtWidgets.QPushButton("Save")

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.addLayout(self.top_line)
        self.layout.addWidget(self.title)
        self.layout.addLayout(form)
        self.layout.addStretch()
        self.layout.addWidget(self.save_button, alignment=QtCore.Qt.AlignCenter)

        # connect signals
        self.back_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(0))
        self.save_button.clicked.connect(self.apply_settings)

    # update settings with user input
    def apply_settings(self):

        # get user input 
        _, scale = self.resolution_options[self.resolution_menue.currentIndex()]
        fps = self.fps_spin.value()

        # update values
        SCALE = float(scale)
        FPS = int(fps)

        QtWidgets.QMessageBox.information(self, "Settings saved", "New settings will be applied on next server start.")


# main page
class MainMenu(QtWidgets.QWidget):
    def __init__(self, stacked_widget):
        super().__init__()

        self.stacked_widget = stacked_widget

        self.settings_button = QtWidgets.QPushButton("Settings")
        self.settings_button.setFixedSize(80, 30)
        self.device_button = QtWidgets.QPushButton("Devices")
        self.device_button.setFixedSize(80, 30)
        self.help_button = QtWidgets.QPushButton("Help")
        self.help_button.setFixedSize(80, 30)

        self.top_line = QtWidgets.QHBoxLayout()
        self.top_line.addStretch()
        self.top_line.addWidget(self.help_button)
        self.top_line.addWidget(self.device_button)
        self.top_line.addWidget(self.settings_button)

        self.title = QtWidgets.QLabel("RC-PC")
        self.title.setStyleSheet("font-size: 24px; margin-bottom: 20px;")
        self.mode = QtWidgets.QLabel("Select Mode")

        # center buttons
        self.client_button = QtWidgets.QPushButton("Client")
        self.client_button.setFixedSize(200, 50)
        self.server_button = QtWidgets.QPushButton("Server")
        self.server_button.setFixedSize(200, 50)

        # layout for center buttons
        self.center_layout = QtWidgets.QVBoxLayout()
        self.center_layout.addWidget(self.title, alignment=QtCore.Qt.AlignHCenter)
        self.center_layout.addWidget(self.mode, alignment=QtCore.Qt.AlignHCenter)
        self.center_layout.addWidget(self.client_button, alignment=QtCore.Qt.AlignHCenter)
        self.center_layout.addWidget(self.server_button, alignment=QtCore.Qt.AlignHCenter)

        # page layout
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.addLayout(self.top_line)
        self.layout.addStretch()
        self.layout.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addLayout(self.center_layout)
        self.layout.addStretch()

        # button presses
        self.client_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(1))
        self.server_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(2))
        self.device_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(3))
        self.settings_button.clicked.connect(lambda: stacked_widget.setCurrentIndex(4))


if __name__ == "__main__":
    # define app
    app = QtWidgets.QApplication([])

    stacked_widget = QtWidgets.QStackedWidget()
    main_menu = MainMenu(stacked_widget)
    client_page = ClientPage(stacked_widget)
    server_page = ServerPage(stacked_widget)
    device_page = DevicePage(stacked_widget)
    settings_page = SettingsPage(stacked_widget)

    # pages 
    stacked_widget.addWidget(main_menu)     # 0
    stacked_widget.addWidget(client_page)   # 1
    stacked_widget.addWidget(server_page)   # 2
    stacked_widget.addWidget(device_page)   # 3
    stacked_widget.addWidget(settings_page) # 4

    stacked_widget.setCurrentIndex(0)   # start on main_menue page
    stacked_widget.resize(800, 600)
    stacked_widget.show()

    sys.exit(app.exec())