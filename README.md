# PlexNFClistener-DAP

This project is a simple Digital Audio Player that gives us a similar feel of a Vinyl player. This is designed keeping in mind to use very less resources of Raspberry Pi. infact, most of the code is written for Raspberry Pi 3A+ with no XServer or desktop. This project uses the power of Framebuffer in Linux. 

* What it is built on?
  Raspberry Pi 3A+,
  PN532 RFID Module (Via I2C connection).
  
  Optional: Waveshare 4.3 inch DSI display, to see Album art and basic track info. If nothing's playing--then it works as a digital clock, by fetching today's Bing Wallpaper as background.

* What are required?
  - Raspberry Pi.
  - Plexamp Headless
  - OS: Raspberry Pi or DietPi. I recommend a non GUI/non xserver minimal install as this project only requires framebuffer for display. For most of the OS setup, I recommend you install Plexamp using OdinBś script https://github.com/odinb/bash-plexamp-installer. It is as simple as running the following line in your already running Raspberry Pi.
```
sudo -i
```
and then
```
bash <(wget -qO- https://raw.githubusercontent.com/odinb/bash-plexamp-installer/main/install_Plexamp_pi.sh)
```


 

  
  
* I do not have PN532 module, can I still run it as just a desktop show and tell display?
  - Yes, you can use it as Desktop show and tell type device. Whatever is running on the headless pi is displayed on the screen.

* What is needed in .env file? And where should I create one?
  - Create it in the folder you are running main.py from. For example:
  ```
  sudo nano /home/pi/plexdap/.env
  ```
1. .env file needs to have these below mwntioned variables.
2. Open weather API key is for displaying Weather information. You can get a free API key in Openweatherś website.
3. LAT and LON are your Latitude and Longitude, which are used to fetch weather information of your exact location.
4. Else, it could get information from CITY information.
5. PLEX Token can be easy to get if you follow this: https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/


```
OPENWEATHER_API_KEY="openweatherapikey"
LAT=yourlatitude
LON=yourlongitude
CITY=yourcity
PLEX_TOKEN="yourplextoken"
PLEX_URL="http://[plexserver_ip_address]:32400/status/sessions/?X-Plex-Token=yourplextoken"
PLEX_BASE_URL="http://[plexserver_ip_address]:32400"
```

* How to run it?
  
  First install fonts and change location of fonts in Time.py and fb.py files.
  
  - Note that I've used this font for clock display code: https://www.1001fonts.com/advanced-led-board-7-font.html
  - For Plexamp Album Display, Iǘe used font family "San Fransico", please install them for good results.
  
  
  And, running main.py is simple. As Raspberry Pi OS comes with Python3, it is as simple as creating a systemctl service to run on the startup.

```
  sudo nano /etc/systemd/system/dap.service 
```
  Paste this in the service file


```
  
[Unit]
Description=Master Code for NFC and Plexamp Art Display
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 /home/pi/plexdap/main.py
Restart=on-failure
User=jay
WorkingDirectory=/home/pi/plexdap
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target



```
  Give permissions to main.py, and run the service.

```
chmod +x /home/pi/plexdap/main.py

sudo systemctl enable dap.service

sudo systemctl start dap.service

sudo systemctl status dap.service
```

Create a webhook listener service also.

Setup webhook in your Plex Server Settings first.

* Plex >>>> Settings >>>> Your Plex Server name >>> Webhooks.
Add http://pi.local:33500/webhook
Remember to change pi.local with your Raspberry Pi hostname or ip address for it to work correctly.

```
  sudo nano /etc/systemd/system/webhook.service 
```
  Paste this in the service file


```
  
[Unit]
Description=Webhook
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 /home/pi/plexdap/webhooklistener.py
Restart=on-failure
User=jay
WorkingDirectory=/home/pi/plexdap
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target



```
  Give permissions to main.py, and run the service.

```
chmod +x /home/pi/plexdap/webhooklistener.py

sudo systemctl enable webhook.service

sudo systemctl start webhook.service

sudo systemctl status webhook.service
```


Restart your pi.

Any thing else recommended?
I recommend running this in a Python virtual environment. Please check main.py, I've used .venv as virtual environment, atleast for running nfc script. Make sure you have all packages installed.

