# PlexNFClistener-DAP

This project is a simple Digital Audio Player that gives us a similar feel of a Vinyl player. This is designed keeping in mind to use very less resources of Raspberry Pi. infact, most of the code is written for Raspberry Pi 3A+ with no XServer or desktop. This project uses the power of Framebuffer in Linux. 

* What it is built on?
  Raspberry Pi 3A+,
  PN532 RFID Module (Via I2C connection).
  
  Optional: Waveshare 4.3 inch DSI display, to see Album art and basic track info. If nothing's playing--then it works as a digital clock, by fetching today's Bing Wallpaper as background.

* How to run it?
  As Raspberry Pi OS comes with Python3, it is as simple as creating a systemctl service to run on the startup.

              sudo nano /etc/systemd/system/my_python_program.service
  Paste this in the service file
  
[Unit]
Description=My Python Program
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/your/main.py
WorkingDirectory=/path/to/your/script/
User=pi
Restart=always
Environment="PYTHONUNBUFFERED=1"
StandardOutput=inherit
StandardError=inherit
RestartSec=5

[Install]
WantedBy=multi-user.target



* I do not have PN532 module, can I still run it as just a desktop show and tell display?
  Yes, you can use it as Desktop show and tell type device. Whatever is running on the headless pi is displayed on the screen.

* 
