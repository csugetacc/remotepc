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

        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing name", "Enter a host device name.")
            return

        client_thread = threading.Thread(target=client.client_program, args=(name,), daemon=True)
        client_thread.start()


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